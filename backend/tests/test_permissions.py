"""权限拦截测试（Day 16）：Day 14 双端分离 + Day 15 角色分级

核心断言就一句：员工看管理接口 → 403；管理员/超管 → 200；无 token → 401。
这组测试把"前端管体验、后端管权限"里的"后端管权限"钉死了。
"""


def test_no_token_cannot_list_users(client):
    """没登录 → 401（连"你是不是员工"都还不知道）"""
    assert client.get("/api/v1/users").status_code == 401


def test_employee_cannot_list_users(client, user_factory, auth_token):
    """员工想拉用户列表 → 403（get_current_admin 拦截）"""
    user_factory("E100", role="employee")
    token = auth_token("E100")
    res = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_department_admin_cannot_list_users(client, user_factory, auth_token):
    user_factory("A100", role="admin", department="销售一部")
    token = auth_token("A100")
    res = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_super_admin_can_list_users(client, user_factory, auth_token):
    user_factory("S100", role="super_admin")
    token = auth_token("S100")
    assert (
        client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )


def test_no_token_cannot_list_documents(client):
    """文档列表同样要登录（Day 14 堵的洞不止上传，列表/删除全要）"""
    assert client.get("/api/v1/documents").status_code == 401


def test_employee_cannot_list_documents(client, user_factory, auth_token):
    user_factory("E100", role="employee")
    token = auth_token("E100")
    assert (
        client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"}).status_code
        == 403
    )


def test_admin_can_list_documents(client, user_factory, auth_token):
    user_factory("A100", role="admin")
    token = auth_token("A100")
    assert (
        client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )
