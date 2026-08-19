"""pytest 全局配置（Day 16）

三个关键设计，每个都是面试点：

1. 内存 SQLite 当测试库 —— 每个测试函数一个全新库，隔离最彻底、跑完即销毁。
   StaticPool 单连接：让所有会话共享同一个内存库（否则每个会话一个空库）。
2. dependency_overrides 替换 get_db —— FastAPI 官方测试姿势：不改任何业务代码，
   把"数据库会话"这个依赖换成测试库的。请求进来拿到的就是测试库。
3. 管理员/超管直接写进测试库 —— 注册接口只出 employee（产品设计），
   测试要造 admin/super_admin 就得绕过接口直接入库。

另外：必须在 import app 之前把 CHROMA_DIR 指到临时目录，
否则 import 时 Chroma 会去开真实的向量库文件，测试和开发可能锁冲突。
"""

import os
import sys
import tempfile
from pathlib import Path

# 1) 必须在 import app 之前：向量库指到临时目录
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="test_chroma_")

# 2) 让测试能找到 backend 里的 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.security import hash_password
from app.database.session import Base
from app.main import app
from app.models.user import User


@pytest.fixture
def engine():
    """每个测试一个全新内存 SQLite"""
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=e)
    yield e
    Base.metadata.drop_all(bind=e)


@pytest.fixture
def client(engine):
    """FastAPI 测试客户端：把 get_db 依赖换成测试库会话"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()  # 测完必须清掉，免得污染下一个测试


@pytest.fixture
def db_session(engine):
    """对测试库的直接会话（造数据/断言库里状态用）"""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = factory()
    yield session
    session.close()


@pytest.fixture
def user_factory(db_session):
    """直接在测试库造任意角色用户，返回其 id

    绕过注册接口的原因：注册强制 role=employee（Day 12 防提权设计），
    测试要造 admin/super_admin，只能直接入库——这也顺便测了"注册进不来高权限"。
    """

    def _make(employee_no, role="employee", password="123456", department=None, name=None):
        user = User(
            employee_no=employee_no,
            name=name or employee_no,
            hashed_password=hash_password(password),
            role=role,
            department=department,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user.id

    return _make


@pytest.fixture
def auth_token(client):
    """走真实登录接口拿 token（顺带验证登录链路本身是通的）"""

    def _token(employee_no, password="123456"):
        res = client.post(
            "/api/v1/users/login",
            json={"employee_no": employee_no, "password": password},
        )
        assert res.status_code == 200, res.text
        return res.json()["access_token"]

    return _token


def auth(token: str) -> dict:
    """拼 Authorization 头，测试文件里直接用"""
    return {"Authorization": f"Bearer {token}"}
