"""把 archive 里的 Olist 真实电商数据 ETL 成 orders 表（Day 26 真实数据测试用）

Olist 是多表数据集，没有"部门/金额/日期"单文件，直接导 import_orders 会缺列。
这里做聚合：order_payments(金额) + customers(客户州当"部门") + orders(下单时间) → 一张 orders 表。

语义代换：department 用 customer_state(客户州)代替——测 NL2SQL 真实能查"各地区订单"，
但"部门"实际是"省份"，不是真企业销售部门(已和用户确认过这个代换)。

用法（在 backend 目录，需 MySQL 在线）：
    ./venv/Scripts/python.exe scripts/import_olist.py <archive目录，默认 d:\...\archive>
"""

import csv
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import SessionLocal
from app.models.order import Order

DEFAULT_ARCHIVE = Path(r"d:\Users\86191\Desktop\archive")
BATCH = 5000  # 分批写，避免一次性 add_all 大列表撑爆


def read_csv(f: Path) -> list[dict]:
    with open(f, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ARCHIVE
    print(f"读取 {archive} ...")

    # 1. 每个订单的付款总额（一个订单可能分多次付款 → SUM）
    amounts: dict[str, Decimal] = defaultdict(Decimal)
    for r in read_csv(archive / "olist_order_payments_dataset.csv"):
        amounts[r["order_id"]] += Decimal(r["payment_value"])
    print(f"有支付记录的订单数：{len(amounts)}")

    # 2. 客户 id → 州（当"部门"）
    cust_state = {
        r["customer_id"]: r["customer_state"]
        for r in read_csv(archive / "olist_customers_dataset.csv")
    }
    print(f"客户数：{len(cust_state)}")

    # 3. 组装 orders：department=州, amount=SUM(付款), created_at=下单时间
    records: list[Order] = []
    for r in read_csv(archive / "olist_orders_dataset.csv"):
        oid = r["order_id"]
        amount = amounts.get(oid)
        if amount is None:
            continue  # 无付款记录(取消/未付)跳过
        state = cust_state.get(r["customer_id"])
        if state is None:
            continue
        dt = datetime.strptime(r["order_purchase_timestamp"], "%Y-%m-%d %H:%M:%S")
        records.append(Order(department=state, amount=amount, created_at=dt))
    print(f"聚合出 {len(records)} 条订单")

    db = SessionLocal()
    db.query(Order).delete()  # 清空旧的(测试用,直接重导)
    db.commit()
    for i in range(0, len(records), BATCH):
        db.add_all(records[i : i + BATCH])
        db.commit()
        print(f"  已写入 {min(i + BATCH, len(records))}/{len(records)}")
    print(f"完成：orders 现在 {db.query(Order).count()} 行")
    db.close()


if __name__ == "__main__":
    main()
