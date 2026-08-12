from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# 创建数据库引擎：FastAPI 通过它跟 MySQL 通信
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# 会话工厂：每个请求用它开一个"数据库会话"
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 所有 ORM 模型的父类：定义表结构的基础
Base = declarative_base()
