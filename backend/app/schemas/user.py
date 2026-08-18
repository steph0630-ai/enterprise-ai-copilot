from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    """注册请求体

    注意：没有 role 字段——角色必须由后端强制（见 user_service.create_user），
    绝不能让客户端自选，否则任何人都能注册成管理员（Day 12 修的漏洞）。
    """
    employee_no: str  # 工号（登录账号，唯一）
    name: str  # 姓名（必填，显示用，可重复）
    password: str
    phone: str | None = None
    email: EmailStr | None = None
    department: str | None = None  # 注册时填的部门（管理员在库里/种子脚本设）

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 位")
        return v


class UserLogin(BaseModel):
    """登录请求体：工号 + 密码（姓名不是登录凭据，重名有歧义）"""
    employee_no: str
    password: str


class UserOut(BaseModel):
    """返回给前端的用户信息（绝不返回 hashed_password）"""
    id: int
    employee_no: str
    name: str
    email: str | None
    phone: str | None
    role: str
    department: str | None

    class Config:
        from_attributes = True  # 允许从 ORM 对象转换
