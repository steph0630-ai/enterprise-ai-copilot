"""Day 12 临时迁移：给已有表加列

背景：create_all 只建新表、不改旧表。今天要给 users 加 department、
给 conversations 加 user_id，就得手动 ALTER。这就是为什么企业要用 Alembic——
这里先用一条条 ALTER 顶着（面试题素材：create_all 不是迁移工具）。

运行（在 backend 目录下）：
    ./venv/Scripts/python.exe scripts/migrate_day12.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.database.session import SessionLocal

ALTERS = [
    # users 表加部门（数据隔离用）
    "ALTER TABLE users ADD COLUMN department VARCHAR(50) NULL",
    # conversations 表加所属用户（会话绑人用）
    "ALTER TABLE conversations ADD COLUMN user_id INT NULL",
]

db = SessionLocal()
try:
    for sql in ALTERS:
        # 幂等保护：列已存在就跳过，重复跑不报错
        column = sql.split(" ")[2]  # 取"department" / "user_id"
        table = "users" if "users" in sql else "conversations"
        exists = db.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
        if exists:
            print(f"[跳过] {table}.{column} 已存在")
            continue
        db.execute(text(sql))
        print(f"[OK] {table} 加列 {column}")
    db.commit()
    print("迁移完成！")
finally:
    db.close()
