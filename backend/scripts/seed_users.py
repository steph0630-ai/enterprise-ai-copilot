"""一次性脚本：建演示用户（1 管理员 + 2 部门员工）（Day 12 权限测试用）

管理员不能通过注册接口创建（注册被强制 employee，防提权），必须走脚本。

运行（在 backend 目录下）：
    ./venv/Scripts/python.exe scripts/seed_users.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.user import User

# (用户名, 密码, 角色, 部门)
USERS = [
    ("admin", "admin123", "admin", None),          # 管理员：可看全部数据
    ("zhangsan", "123456", "employee", "销售一部"),  # 员工：只能看销售一部
    ("lisi", "123456", "employee", "市场部"),        # 员工：只能看市场部
]

db = SessionLocal()
try:
    for username, password, role, department in USERS:
        if db.query(User).filter(User.username == username).first():
            print(f"[跳过] {username} 已存在")
            continue
        db.add(
            User(
                username=username,
                hashed_password=hash_password(password),
                role=role,
                department=department,
            )
        )
        print(f"[OK] 创建 {username}（{role}，部门：{department or '不限'}）")
    db.commit()
    print("种子用户就绪！")
finally:
    db.close()
