from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


def get_by_employee_no(db: Session, employee_no: str) -> User | None:
    """按工号查用户（工号唯一，是登录账号）"""
    return db.query(User).filter(User.employee_no == employee_no).first()


def create_user(db: Session, data: UserCreate) -> User:
    """注册：先查重，再加密密码入库"""
    if get_by_employee_no(db, data.employee_no):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="工号已存在"
        )
    user = User(
        employee_no=data.employee_no,
        name=data.name,  # Day 13：姓名必填（显示用，可重复）
        email=data.email,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        # 安全：角色永远强制 employee，禁止客户端自封管理员（Day 12 修漏洞）
        role="employee",
        department=data.department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, employee_no: str, password: str) -> User:
    """登录：校验工号 + 密码"""
    user = get_by_employee_no(db, employee_no)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="工号或密码错误"
        )
    return user