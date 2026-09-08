from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase, KnowledgeBaseMember
from app.services import knowledge_base_service
from conftest import auth


def _kb(db, kb_id, name, owner_id, visibility="private", department=None):
    item = KnowledgeBase(
        id=kb_id,
        name=name,
        owner_id=owner_id,
        visibility=visibility,
        department=department,
    )
    db.add(item)
    db.commit()
    return item


def test_visibility_and_member_rules(db_session, user_factory):
    owner = user_factory("A100", role="admin")
    sales = user_factory("E100", department="销售部")
    marketing = user_factory("E200", department="市场部")
    private = _kb(db_session, 1, "私有", owner)
    _kb(db_session, 2, "销售部", owner, "department", "销售部")
    _kb(db_session, 3, "公开", owner, "public")
    db_session.add(KnowledgeBaseMember(knowledge_base_id=private.id, user_id=marketing))
    db_session.commit()

    from app.models.user import User
    assert {kb.id for kb in knowledge_base_service.list_accessible(db_session, db_session.get(User, sales))} == {2, 3}
    assert {kb.id for kb in knowledge_base_service.list_accessible(db_session, db_session.get(User, marketing))} == {1, 3}


def test_retrieval_scope_uses_only_accessible_documents(db_session, user_factory):
    from app.models.user import User

    owner = user_factory("A100", role="admin")
    employee = user_factory("E100", department="销售部")
    _kb(db_session, 1, "私有", owner)
    _kb(db_session, 2, "销售部", owner, "department", "销售部")
    _kb(db_session, 3, "公开", owner, "public")
    for doc_id, kb_id in ((11, 1), (22, 2), (33, 3)):
        db_session.add(
            Document(
                id=doc_id,
                knowledge_base_id=kb_id,
                filename=f"{doc_id}.pdf",
                file_path=f"files/{doc_id}.pdf",
                status="processed",
            )
        )
    db_session.commit()

    user = db_session.get(User, employee)
    assert knowledge_base_service.accessible_document_ids(db_session, user) == [22, 33]
    assert knowledge_base_service.accessible_document_ids(db_session, user, 2) == [22]


def test_knowledge_base_list_includes_document_count(
    client, db_session, user_factory, auth_token
):
    owner = user_factory("S100", role="super_admin")
    _kb(db_session, 1, "资料库", owner, "public")
    db_session.add_all(
        [
            Document(
                knowledge_base_id=1,
                filename=f"{n}.txt",
                file_path=f"files/{n}.txt",
                status="processed",
            )
            for n in range(2)
        ]
    )
    db_session.commit()

    rows = client.get(
        "/api/v1/knowledge-bases", headers=auth(auth_token("S100"))
    ).json()
    assert rows[0]["document_count"] == 2


def test_cannot_select_inaccessible_knowledge_base(client, db_session, user_factory, auth_token):
    owner = user_factory("A100", role="admin")
    user_factory("E100", department="销售部")
    _kb(db_session, 1, "私有", owner)
    token = auth_token("E100")

    res = client.post(
        "/api/v1/knowledge/search",
        json={"query": "机密", "knowledge_base_id": 1},
        headers=auth(token),
    )
    assert res.status_code == 404


def test_super_admin_can_add_member(client, db_session, user_factory, auth_token):
    owner = user_factory("A100", role="super_admin")
    member = user_factory("E100")
    _kb(db_session, 1, "私有", owner)
    token = auth_token("A100")

    assert client.post(
        "/api/v1/knowledge-bases/1/members",
        json={"user_id": member},
        headers=auth(token),
    ).status_code == 201
    employee_token = auth_token("E100")
    visible = client.get("/api/v1/knowledge-bases", headers=auth(employee_token)).json()
    assert [kb["id"] for kb in visible] == [1]


def test_department_admin_only_accesses_and_manages_own_department(
    client, db_session, user_factory, auth_token
):
    admin = user_factory("A100", role="admin", department="销售部")
    other = user_factory("A200", role="admin", department="市场部")
    private = _kb(db_session, 1, "私有", admin)
    _kb(db_session, 2, "销售部", other, "department", "销售部")
    _kb(db_session, 3, "市场部", other, "department", "市场部")
    _kb(db_session, 4, "公开", other, "public")
    db_session.add(KnowledgeBaseMember(knowledge_base_id=private.id, user_id=admin))
    db_session.commit()

    token = auth_token("A100")
    visible = client.get("/api/v1/knowledge-bases", headers=auth(token)).json()
    assert {kb["id"] for kb in visible} == {2, 4}
    assert {kb["id"] for kb in visible if kb["can_manage"]} == {2}
    assert client.get("/api/v1/documents?knowledge_base_id=3", headers=auth(token)).status_code == 404
    assert client.post(
        "/api/v1/documents/upload",
        data={"knowledge_base_id": "3"},
        files={"file": ("secret.txt", b"secret", "text/plain")},
        headers=auth(token),
    ).status_code == 404


def test_department_admin_creation_is_forced_to_own_department(
    client, user_factory, auth_token
):
    user_factory("A100", role="admin", department="销售部")
    token = auth_token("A100")
    res = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "销售资料", "visibility": "public"},
        headers=auth(token),
    )
    assert res.status_code == 201
    assert res.json()["visibility"] == "department"
    assert res.json()["department"] == "销售部"


def test_department_admin_without_department_cannot_create(
    client, user_factory, auth_token
):
    user_factory("A100", role="admin")
    res = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "无部门库"},
        headers=auth(auth_token("A100")),
    )
    assert res.status_code == 403


def test_changing_private_knowledge_base_clears_members(
    client, db_session, user_factory, auth_token
):
    owner = user_factory("S100", role="super_admin")
    member = user_factory("E100")
    _kb(db_session, 1, "私有库", owner)
    db_session.add(KnowledgeBaseMember(knowledge_base_id=1, user_id=member))
    db_session.commit()
    headers = auth(auth_token("S100"))

    assert client.put(
        "/api/v1/knowledge-bases/1",
        json={"name": "公开库", "visibility": "public"},
        headers=headers,
    ).status_code == 200
    assert db_session.query(KnowledgeBaseMember).count() == 0

    assert client.put(
        "/api/v1/knowledge-bases/1",
        json={"name": "再次私有", "visibility": "private"},
        headers=headers,
    ).status_code == 200
    visible = client.get(
        "/api/v1/knowledge-bases", headers=auth(auth_token("E100"))
    ).json()
    assert visible == []


def test_cannot_add_member_to_non_private_knowledge_base(
    client, db_session, user_factory, auth_token
):
    owner = user_factory("S100", role="super_admin")
    member = user_factory("E100")
    _kb(db_session, 1, "公开库", owner, "public")
    res = client.post(
        "/api/v1/knowledge-bases/1/members",
        json={"user_id": member},
        headers=auth(auth_token("S100")),
    )
    assert res.status_code == 400
