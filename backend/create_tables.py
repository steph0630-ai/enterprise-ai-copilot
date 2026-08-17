"""建表脚本：运行 python create_tables.py 把模型对应的表建进数据库

注意：
- create_all 只"新建不存在的表"，不"修改已存在的表"。
- 以后改表结构（加字段等）要用迁移工具 Alembic，不是重跑这个脚本。
"""
from app.database.session import Base, engine
from app import models  # 触发 models/__init__.py，让 SQLAlchemy 认识所有模型

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("[OK] 建表完成！当前所有表：")
    for table in Base.metadata.sorted_tables:
        print("  -", table.name)
