"""一次性脚本：把【真实】订单 CSV 导入 orders 表，用它真实测 NL2SQL（Day 26 收尾）

不用造演示数据——直接导入你业务系统导出的真实订单，NL2SQL 才有真数据可查。

用法（在 backend 目录，需 Docker/MySQL 已起）：
    ./venv/Scripts/python.exe scripts/import_orders.py 你的订单.csv
    ./venv/Scripts/python.exe scripts/import_orders.py 你的订单.csv --replace   # 先清空 orders 再导
    ./venv/Scripts/python.exe scripts/import_orders.py 你的订单.csv --dry-run  # 只解析打印，不写库

CSV 列名自动识别（常见写法都能认，缺一列会明确报错）：
    - 部门    : 部门 / department / 部门名 / 所属部门 / 部门名称
    - 金额    : 金额 / amount / 订单金额 / 金额(元) / 总额
    - 下单时间: 日期 / created_at / 下单日期 / 时间 / 订单日期 / 下单时间
编码自动尝试 UTF-8-sig / GBK / UTF-8（Windows 业务导出常见 GBK）。
"""

import argparse
import csv
import io
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import SessionLocal
from app.models.order import Order


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


COL_MAP = {
    "department": ["部门", "department", "部门名", "所属部门", "部门名称"],
    "amount": ["金额", "amount", "订单金额", "金额(元)", "金额（元）", "总额"],
    "created_at": ["日期", "created_at", "下单日期", "时间", "订单日期", "下单时间"],
}


def detect_cols(headers) -> dict:
    """按表头里的关键词自动定位三列，返回 {字段名: 实际列名}"""
    cols = {}
    for h in headers:
        hn = _norm(h)
        for key, names in COL_MAP.items():
            if key not in cols and any(n in hn for n in names):
                cols[key] = h
    return cols


def parse_amount(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace("¥", "").replace("￥", "") \
        .replace("元", "").replace(" ", "")
    try:
        return Decimal(s)
    except Exception:
        return None


def parse_date(v):
    if not v:
        return None
    v = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="真实订单 CSV 文件路径")
    ap.add_argument("--replace", action="store_true", help="先清空原 orders 再导入")
    ap.add_argument("--dry-run", action="store_true", help="解析并打印，不写库")
    a = ap.parse_args()

    p = Path(a.path)
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    else:
        sys.exit("无法解码文件，请确认是 UTF-8 或 GBK 编码")

    rows = list(csv.DictReader(io.StringIO(txt)))
    if not rows:
        sys.exit("CSV 没有数据行")
    cols = detect_cols(rows[0].keys())
    missing = [k for k in ("department", "amount", "created_at") if k not in cols]
    if missing:
        sys.exit(
            f"缺列（无法自动识别）: {missing}；你文件的表头是 {list(rows[0].keys())}"
        )

    print(f"识别到列 → 部门={cols['department']} | 金额={cols['amount']} | 日期={cols['created_at']}")
    print(f"共 {len(rows)} 行")

    records = []
    skipped = 0
    for r in rows:
        amt = parse_amount(r[cols["amount"]])
        if amt is None:
            skipped += 1
            continue
        dt = parse_date(r[cols["created_at"]])
        if dt is None:
            dt = datetime.now()  # 日期解析不了就用当前时间，别丢行
        records.append(Order(department=(r[cols["department"]] or "").strip(),
                             amount=amt, created_at=dt))
    print(f"有效 {len(records)} 条（金额解析失败跳过 {skipped} 条；日期异常用当前时间兜底）")

    if a.dry_run:
        print("dry-run：只解析，未写库")
        return

    db = SessionLocal()
    if a.replace:
        db.query(Order).delete()
        db.commit()
        print("已清空原 orders")
    db.add_all(records)
    db.commit()
    print(f"已写入 {len(records)} 条到 orders，关闭连接")
    db.close()


if __name__ == "__main__":
    main()
