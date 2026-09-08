from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_super_admin,
    get_current_user,
    get_db,
)
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserDepartmentUpdate,
    UserLogin,
    UserOut,
    UserRoleUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    """注册：校验 → 服务层查重/加密 → 入库"""
    return user_service.create_user(db, data)


@router.post("/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    """登录：验证工号密码 → 生成 JWT 返回"""
    user = user_service.authenticate(db, data.employee_no, data.password)
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """带 token 访问：返回当前登录用户"""
    return current_user


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    """用户列表（仅超级管理员可用）"""
    return db.query(User).order_by(User.id).all()


@router.put("/{user_id}/department", response_model=UserOut)
def update_user_department(
    user_id: int,
    data: UserDepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_super_admin),
):
    """超级管理员分配或清除员工部门；注册者不能自行设置。"""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role == "admin" and data.department is None:
        raise HTTPException(status_code=400, detail="请先将部门管理员降级为员工")
    user.department = data.department
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: Session = Depends(get_db),
    # Day 15：只有超级管理员能改角色。普通管理员无"授予权限"的能力，
    # 否则会出现：A 升 X 为 admin → X 反手把 A 降成员工（提权劫持）。
    current_user: User = Depends(get_current_super_admin),
):
    """改角色（超级管理员专用）：只能 employee ↔ admin 之间切换

    安全点（Day 15 收紧）：
    - 超级管理员不能改自己 → 防止自己把自己锁死（root 是最后的保险）；
    - 超级管理员的角色不能通过接口改 → 防止 root 被另一个 root 夺权；
    - 不能通过接口授予超级管理员 → 防止 root"克隆"出第二个自己再被反噬。
    super_admin 这个角色只进不出，只能由运维/种子脚本创建（如 E001）。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    if user.role == "super_admin":
        raise HTTPException(status_code=400, detail="超级管理员的角色不能通过接口修改")
    if data.role == "super_admin":
        raise HTTPException(status_code=400, detail="不能通过接口授予超级管理员")
    if data.role == "admin" and not user.department:
        raise HTTPException(status_code=400, detail="请先为该用户分配部门")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user
