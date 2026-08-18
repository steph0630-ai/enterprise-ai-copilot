import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.user import User

# HTTPBearer：从 Authorization 头拿 "Bearer <token>"，Swagger 可直接粘贴 token
http_bearer = HTTPBearer(auto_error=False)


def get_db():
    """每个请求一个数据库会话，用完必须关闭，防止连接泄漏"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """从 JWT 解析用户：验签 → 取 user id → 查库返回当前用户"""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exc
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except jwt.PyJWTError:
        raise credentials_exc

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exc
    return user


# 能进管理后台的角色（Day 15：super_admin 也是管理端的一员）
ADMIN_ROLES = {"admin", "super_admin"}


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """管理接口专用：admin 或 super_admin，否则 403（Day 14 双端分离的核心拦截）"""
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限"
        )
    return current_user


def get_current_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """超级管理员专用：只有 super_admin，否则 403（Day 15 防提权劫持）

    只有它能改角色——普通管理员没有"授予权限"的能力，
    提权劫持（员工升 admin 后反手降 admin）的链条第一步就断了。
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限"
        )
    return current_user
