from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserOut, UserRoleUpdate
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
    current_user: User = Depends(get_current_admin),  # Day 14：只有管理员能看全部用户
):
    """用户列表（管理端用）"""
    return db.query(User).order_by(User.id).all()


@router.put("/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),  # Day 14：只有管理员能改角色
):
    """改角色（管理端用）：把员工提升为 admin / 把 admin 降为员工

    安全点：管理员不能改自己——否则把自己降成 employee，下次请求直接 403，
    整个系统就没人能管理了（自己把自己锁死）。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user