from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    """注册请求体"""
    username: str
    password: str
    email: EmailStr | None = None
    role: str = "employee"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 位")
        return v


class UserLogin(BaseModel):
    """登录请求体"""
    username: str
    password: str


class UserOut(BaseModel):
    """返回给前端的用户信息（绝不返回 hashed_password）"""
    id: int
    username: str
    email: str | None
    role: str

    class Config:
        from_attributes = True  # 允许从 ORM 对象转换
