"""认证链路测试（Day 16）：注册 / 查重 / 登录 / /me / 无 token

覆盖了 Day 12（注册强制 employee、防提权）和 Day 13（工号唯一）的核心行为。
"""


def register(client, employee_no="E100", password="123456", name="测试"):
    """注册一个普通员工，返回响应对象"""
    return client.post(
        "/api/v1/users/register",
        json={"employee_no": employee_no, "name": name, "password": password},
    )


def test_register_success(client):
    """注册成功：工号/姓名返回，且角色永远是 employee（Day 12 防提权）"""
    res = register(client)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["employee_no"] == "E100"
    assert data["name"] == "测试"
    assert data["role"] == "employee"  # 关键：注册不可能自封管理员


def test_register_duplicate_employee_no(client):
    """工号查重（Day 13）：同一工号再注册 → 400"""
    assert register(client).status_code == 201
    res = register(client)
    assert res.status_code == 400
    assert "工号已存在" in res.json()["detail"]


def test_register_duplicate_employee_no_ignores_different_name(client):
    """姓名可重复，工号才查重——不同工号、相同姓名都能注册（Day 13 设计）"""
    assert register(client, employee_no="E100", name="张三").status_code == 201
    assert register(client, employee_no="E101", name="张三").status_code == 201


def test_register_password_too_short(client):
    """密码至少 6 位（schema 校验）"""
    res = register(client, password="123")
    assert res.status_code == 422


def test_login_wrong_password(client):
    register(client)
    res = client.post(
        "/api/v1/users/login", json={"employee_no": "E100", "password": "wrong"}
    )
    assert res.status_code == 401


def test_login_no_such_employee(client):
    """不存在的工号登录 → 401"""
    res = client.post(
        "/api/v1/users/login", json={"employee_no": "NOBODY", "password": "123456"}
    )
    assert res.status_code == 401


def test_me_requires_token(client):
    """/me 没带 token → 401（JWT 保护）"""
    assert client.get("/api/v1/users/me").status_code == 401


def test_me_with_valid_token(client, auth_token):
    """带 token 访问 /me → 返回当前用户"""
    register(client, employee_no="E200")
    token = auth_token("E200")
    res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["employee_no"] == "E200"
    # 响应绝不含密码哈希（安全）
    assert "hashed_password" not in res.json()


def test_knowledge_routes_require_token(client):
    """旧版检索/问答接口也必须登录，不能绕过 Agent 的鉴权。"""
    for path in ("/api/v1/knowledge/search", "/api/v1/chat"):
        res = client.post(path, json={"query": "报销流程"})
        assert res.status_code == 401, (path, res.text)


def test_knowledge_routes_accept_valid_token(
    client, user_factory, auth_token, monkeypatch
):
    """合法 JWT 通过鉴权，并能正常进入原有检索/问答处理。"""
    from app.api.v1 import chat as chat_api
    from app.api.v1 import knowledge as knowledge_api

    user_factory("E300")
    token = auth_token("E300")
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setattr(knowledge_api.retrieval_service, "search", lambda q, k: [])
    monkeypatch.setattr(
        chat_api.rag_service,
        "answer",
        lambda q, k: {"answer": "测试回答", "sources": []},
    )

    search_res = client.post(
        "/api/v1/knowledge/search",
        json={"query": "报销流程"},
        headers=headers,
    )
    chat_res = client.post(
        "/api/v1/chat",
        json={"query": "报销流程"},
        headers=headers,
    )

    assert search_res.status_code == 200, search_res.text
    assert chat_res.status_code == 200, chat_res.text
