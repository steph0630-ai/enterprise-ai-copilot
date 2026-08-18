from sqlalchemy import Column, Integer, String, DateTime, func

from app.database.session import Base


class User(Base):
    """用户表模型：一个 Python 类 = 一张表"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)  # 登录名，唯一
    email = Column(String(120), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)  # 只存加密后的密码
    role = Column(String(20), default="employee")  # employee / admin
    department = Column(String(50), nullable=True)  # 所属部门（Day 12 数据隔离）
    phone = Column(String(20), unique=True, index=True, nullable=True)
    created_time = Column(DateTime(timezone=True), server_default=func.now())
