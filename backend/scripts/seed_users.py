"""一次性脚本：建演示用户（1 管理员 + 2 部门员工）（Day 12 权限测试用）

Day 13 改造：
- 登录账号从 username 改成工号 employee_no（E001/E002/E003）
- 新增必填姓名 name（显示用）
- 改成"幂等更新"（upsert）：工号存在就更新，不存在才创建，重复跑不会炸

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

# (工号, 密码, 角色, 部门, 姓名)
USERS = [
    {"employee_no": "E001", "password": "admin123", "role": "admin", "department": None, "name": "管理员"},
    {"employee_no": "E002", "password": "123456", "role": "employee", "department": "销售一部", "name": "张三"},
    {"employee_no": "E003", "password": "123456", "role": "employee", "department": "市场部", "name": "李四"},
]

db = SessionLocal()
try:
    # 老演示账号升级：Day 13 之前工号是 admin/zhangsan/lisi，改成 E001/E002/E003。
    # 会话是按 user_id 绑的，工号改掉不影响历史会话。
    LEGACY_RENAME = {"admin": "E001", "zhangsan": "E002", "lisi": "E003"}
    for old_no, new_no in LEGACY_RENAME.items():
        old = db.query(User).filter(User.employee_no == old_no).first()
        if old and not db.query(User).filter(User.employee_no == new_no).first():
            old.employee_no = new_no
            print(f"[升级] 老工号 {old_no} → {new_no}")

    # 关键：先把"升级"落库。SessionLocal 是 autoflush=False，
    # 升级只改了内存对象、数据库没动；不 commit 的话，下面"查重 E001"
    # 查到的是旧库（还没有 E001），就会再建一个 → 唯一索引冲突。
    db.commit()

    for u in USERS:
        existing = db.query(User).filter(User.employee_no == u["employee_no"]).first()
        if existing:
            # 已存在 → 更新信息（重复跑也安全）
            existing.name = u["name"]
            existing.role = u["role"]
            existing.department = u["department"]
            existing.hashed_password = hash_password(u["password"])
            print(f"[更新] {u['employee_no']}（{u['name']}）")
        else:
            db.add(
                User(
                    employee_no=u["employee_no"],
                    name=u["name"],
                    hashed_password=hash_password(u["password"]),
                    role=u["role"],
                    department=u["department"],
                )
            )
            print(f"[创建] {u['employee_no']}（{u['name']}）")
    db.commit()
    print("种子用户就绪！")
finally:
    db.close()
