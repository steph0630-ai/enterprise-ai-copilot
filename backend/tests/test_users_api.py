"""用户/角色管理测试（Day 16）：Day 15 的"root 只进不出"规则

六条安全规则，每条一个测试：
- 员工改角色 → 403（连入口都没有）
- 普通管理员改角色 → 403（没有授予权）
- 超管升员工为管理员 → 200
- 超管授予 super_admin → 400（不能克隆 root）
- 超管动另一个超管 → 400（root 不能被接口动摇）
- 超管改自己 → 400（防自锁）
"""


def test_employee_cannot_change_department(client, user_factory, auth_token):
    user_factory("E100", role="employee", department="销售一部")
    target_id = user_factory("E200", role="employee")
    token = auth_token("E100")
    res = client.put(
        f"/api/v1/users/{target_id}/department",
        json={"department": "财务部"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_admin_can_assign_and_clear_department(client, user_factory, auth_token):
    user_factory("A100", role="admin")
    target_id = user_factory("E200", role="employee")
    token = auth_token("A100")
    headers = {"Authorization": f"Bearer {token}"}

    assigned = client.put(
        f"/api/v1/users/{target_id}/department",
        json={"department": "  财务部  "},
        headers=headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["department"] == "财务部"

    cleared = client.put(
        f"/api/v1/users/{target_id}/department",
        json={"department": None},
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["department"] is None


def test_employee_cannot_change_role(client, user_factory, auth_token):
    user_factory("E100", role="employee")
    target_id = user_factory("E200", role="employee")
    token = auth_token("E100")
    res = client.put(
        f"/api/v1/users/{target_id}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_admin_cannot_change_role(client, user_factory, auth_token):
    """普通管理员没有授予权（Day 15 关键：提权劫持链条第一步就断）"""
    user_factory("A100", role="admin")
    target_id = user_factory("E200", role="employee")
    token = auth_token("A100")
    res = client.put(
        f"/api/v1/users/{target_id}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_super_admin_can_promote_employee(client, user_factory, auth_token):
    user_factory("S100", role="super_admin")
    target_id = user_factory("E200", role="employee")
    token = auth_token("S100")
    res = client.put(
        f"/api/v1/users/{target_id}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "admin"


def test_super_admin_can_demote_admin(client, user_factory, auth_token):
    user_factory("S100", role="super_admin")
    target_id = user_factory("A200", role="admin")
    token = auth_token("S100")
    res = client.put(
        f"/api/v1/users/{target_id}/role",
        json={"role": "employee"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "employee"


def test_cannot_grant_super_admin(client, user_factory, auth_token):
    """超管不能把别人设成 super_admin（防克隆→反噬）"""
    user_factory("S100", role="super_admin")
    target_id = user_factory("E200", role="employee")
    token = auth_token("S100")
    res = client.put(
        f"/api/v1/users/{target_id}/role",
        json={"role": "super_admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "授予" in res.json()["detail"]


def test_cannot_modify_other_super_admin(client, user_factory, auth_token):
    """另一个 super_admin 也不能被接口改（root 只进不出）"""
    user_factory("S100", role="super_admin")
    s200_id = user_factory("S200", role="super_admin")
    token = auth_token("S100")
    res = client.put(
        f"/api/v1/users/{s200_id}/role",
        json={"role": "employee"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400


def test_cannot_change_own_role(client, user_factory, auth_token):
    """超管不能改自己（防自锁）"""
    own_id = user_factory("S100", role="super_admin")
    token = auth_token("S100")
    res = client.put(
        f"/api/v1/users/{own_id}/role",
        json={"role": "employee"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "自己" in res.json()["detail"]


def test_invalid_role_value_422(client, user_factory, auth_token):
    """乱传角色名 → 422（schema 校验）"""
    user_factory("S100", role="super_admin")
    target_id = user_factory("E200", role="employee")
    token = auth_token("S100")
    res = client.put(
        f"/api/v1/users/{target_id}/role",
        json={"role": "boss"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422
