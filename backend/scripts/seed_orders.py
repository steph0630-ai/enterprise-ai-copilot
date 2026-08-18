"""一次性脚本：建 orders 表并塞入演示数据（Agent 数据工具用）

运行（在 backend 目录下）：
    ./venv/Scripts/python.exe scripts/seed_orders.py
"""

import sys
from pathlib import Path

# 把 backend 根目录加进模块搜索路径：
# 直接运行 scripts/xxx.py 时，Python 默认只找得到 scripts/ 里的模块，
# 找不到 app 包。手动把项目根目录加进来才能 `from app... import`。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime

from app.database.session import Base, engine, SessionLocal
from app.models.order import Order  # noqa: F401  必须 import，create_all 才知道这张表

# 1. 建表（create_all 只建"不存在的表"，已存在的不会动）
Base.metadata.create_all(bind=engine)

# 2. 塞演示数据（表里已有数据就跳过，别重复插）
db = SessionLocal()
try:
    if db.query(Order).count() > 0:
        print("orders 表已有数据，跳过")
    else:
        rows = [
            # 销售一部：3 笔，共 45000
            Order(department="销售一部", amount=8000, created_at=datetime(2026, 8, 3)),
            Order(department="销售一部", amount=15000, created_at=datetime(2026, 8, 10)),
            Order(department="销售一部", amount=22000, created_at=datetime(2026, 8, 15)),
            # 销售二部：2 笔，共 30000
            Order(department="销售二部", amount=12000, created_at=datetime(2026, 8, 5)),
            Order(department="销售二部", amount=18000, created_at=datetime(2026, 8, 12)),
            # 市场部：2 笔，共 14000
            Order(department="市场部", amount=5000, created_at=datetime(2026, 8, 8)),
            Order(department="市场部", amount=9000, created_at=datetime(2026, 8, 16)),
        ]
        db.add_all(rows)
        db.commit()
        print(f"已插入 {len(rows)} 条订单")
finally:
    db.close()
