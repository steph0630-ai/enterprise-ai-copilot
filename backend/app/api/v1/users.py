from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserOut
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