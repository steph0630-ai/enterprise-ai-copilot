"""文档管理接口测试（Day 16）

Day 14 的核心修复就是：文档上传从"谁都能传"变成"只有管理员能传"。
这组测试把修复钉死——员工上传 → 403，管理员上传 → 200。

Mock 原则：save_uploaded_file（不写真实磁盘）和 ingest_document（不调 embedding，
不花钱）都打桩。测试只关心"权限 + 接口链路"，不关心向量化的内部实现。
"""

from fastapi.testclient import TestClient

from app.services import document_service


def upload(client: TestClient, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        headers=headers,
    )


def test_upload_requires_login(client):
    """不带 token 上传 → 401（Day 14 堵住的洞）"""
    assert upload(client).status_code == 401


def test_employee_cannot_upload(client, user_factory, auth_token):
    """员工上传 → 403"""
    user_factory("E100", role="employee")
    token = auth_token("E100")
    assert upload(client, token).status_code == 403


def test_admin_can_upload(client, user_factory, auth_token, monkeypatch):
    """管理员上传 → 200（mock 掉写盘和向量化）"""
    # 打桩：不写真实磁盘、不调 embedding（省时间省钱）
    monkeypatch.setattr(
        document_service, "save_uploaded_file", lambda content, filename: f"app/storage/files/{filename}"
    )
    monkeypatch.setattr(document_service, "ingest_document", lambda db, doc_id, filename: 3)

    user_factory("A100", role="admin")
    token = auth_token("A100")
    res = upload(client, token)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["chunk_count"] == 3
    assert data["status"] == "processed"
    assert data["document_id"] > 0


def test_delete_document_by_employee_forbidden(client, user_factory, auth_token, db_session):
    """员工删除 → 403"""
    from app.models.document import Document

    doc = Document(filename="old.pdf", file_path="app/storage/files/old.pdf", knowledge_base_id=1)
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    user_factory("E100", role="employee")
    token = auth_token("E100")
    res = client.delete(f"/api/v1/documents/{doc.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_delete_document_by_admin(client, user_factory, auth_token, db_session):
    """管理员删除 → 200，且记录从库里消失"""
    from app.models.document import Document

    doc = Document(filename="old.pdf", file_path="app/storage/files/old.pdf", knowledge_base_id=1)
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    user_factory("A100", role="admin")
    token = auth_token("A100")
    res = client.delete(f"/api/v1/documents/{doc.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    # 用 COUNT 查询断言库里没了：绕开身份映射缓存（db_session 之前 load 过 doc，
    # 直接 get 会返回缓存旧对象；COUNT 是直接查库，不碰缓存）
    assert db_session.query(Document).filter(Document.id == doc.id).count() == 0


def test_delete_missing_document_404(client, user_factory, auth_token):
    """删不存在的文档 → 404"""
    user_factory("A100", role="admin")
    token = auth_token("A100")
    res = client.delete("/api/v1/documents/99999", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404
