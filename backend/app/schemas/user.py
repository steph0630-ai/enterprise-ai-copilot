from pydantic import BaseModel, EmailStr, Field, field_validator


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

    # 注册接口不接受 role / department 等权限字段，防止客户端自行声明身份。
    model_config = {"extra": "forbid"}

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


class UserRoleUpdate(BaseModel):
    """改角色请求体（Day 14 新增，Day 15 加 super_admin）

    只允许在 employee / admin / super_admin 之间切换。
    注意：谁能调这个接口由 deps.get_current_super_admin 把关（只有超级管理员能改角色）。
    """

    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("employee", "admin", "super_admin"):
            raise ValueError("角色只能是 employee / admin / super_admin")
        return v


class UserDepartmentUpdate(BaseModel):
    """管理员分配部门；传 null 表示取消分配。"""

    department: str | None = Field(default=None, max_length=50)

    @field_validator("department")
    @classmethod
    def normalize_department(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        if not value:
            raise ValueError("部门不能为空字符串；取消分配请传 null")
        return value


class UserOut(BaseModel):
    """返回给前端的用户信息（绝不返回 hashed_password）"""
    id: int
    employee_no: str
    name: str
    email: str | None
    phone: str | None
    role: str
    department: str | None

    # Pydantic V2 新写法（旧 class Config 已弃用）：允许从 ORM 对象转换
    model_config = {"from_attributes": True}
