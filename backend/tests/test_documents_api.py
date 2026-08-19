"""文档管理接口测试（Day 16 创建 / Day 18 改成异步入库后重写）

Day 14 的核心修复：文档上传从"谁都能传"变成"只有管理员能传"。
Day 18 的改造：上传变成异步——接口只收文件+建记录，后台任务慢慢入库。

Mock 原则：
- save_uploaded_file（不写真实磁盘）、ingest_document_job（不打真实后台任务）
  都打桩，API 测试只关心"权限 + 接口链路"。
- 后台任务 ingest_document_job 单独测：打桩 SessionLocal / parse_pdf / embedding，
  直接调用，验证状态流转 + 入库。
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services import document_service
from app.vectorstore.store import vector_store


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


def test_admin_can_upload_returns_immediately(client, user_factory, auth_token, monkeypatch):
    """管理员上传 → 200，且秒回"uploading"（不再等入库）

    Day 18 异步契约：接口只负责收文件+建记录，返回 status="uploading"。
    后台任务打成 no-op——TestClient 会在响应后真的跑 BackgroundTasks，
    不能让它碰真实 SessionLocal（MySQL）和 embedding。
    """
    # 打桩：不写真实磁盘、后台任务不真跑
    monkeypatch.setattr(
        document_service, "save_uploaded_file", lambda src, filename: f"app/storage/files/{filename}"
    )
    monkeypatch.setattr(document_service, "ingest_document_job", lambda doc_id, filename: None)

    user_factory("A100", role="admin")
    token = auth_token("A100")
    res = upload(client, token)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "uploading"  # 不再是 processed——入库还在后台
    assert data["document_id"] > 0


def test_upload_too_large_413(client, user_factory, auth_token, monkeypatch):
    """超过大小上限 → 413（Day 18 流式写盘中途拒绝）"""
    from app.core.config import settings

    # 把上限调小到 10 字节，超过就 413
    monkeypatch.setattr(settings, "MAX_DOC_SIZE", 10)
    monkeypatch.setattr(document_service, "ingest_document_job", lambda doc_id, filename: None)

    user_factory("A100", role="admin")
    token = auth_token("A100")
    res = upload(client, token)
    assert res.status_code == 413, res.text


# ========== 后台入库任务（ingest_document_job）==========

def _setup_doc(db_session, status="uploading"):
    """在测试库建一条 documents 记录，返回 doc"""
    doc = Document(filename="job.pdf", file_path="app/storage/files/job.pdf", knowledge_base_id=1, status=status)
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _patch_job_deps(monkeypatch, engine, chunks, fail=False):
    """让后台任务用测试库 + 假解析 + 假向量，绝不碰真实 MySQL/API"""
    # 1) SessionLocal → 测试库的会话工厂（否则 job 会开真实 MySQL 连接）
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(document_service, "SessionLocal", factory)
    # 2) 假 PDF 解析：返回固定文本
    monkeypatch.setattr(document_service, "parse_pdf", lambda path: chunks)
    # 2.5) 假切分：原样返回（不然太短的假文本会被并成一个 chunk，数量不好断言）
    monkeypatch.setattr(document_service, "split_text", lambda pages: pages)
    # 3) 假 embedding：每条文本一个 4 维假向量，或直接抛错模拟失败
    def fake_embed(texts):
        if fail:
            raise RuntimeError("embedding 服务挂了")
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]
    monkeypatch.setattr(document_service.embedding_service, "embed_documents", fake_embed)


def test_ingest_job_marks_processed(db_session, engine, monkeypatch):
    """后台任务成功：状态 uploading → processed，chunk 进库、向量入 Chroma"""
    doc = _setup_doc(db_session)
    _patch_job_deps(monkeypatch, engine, ["第一段文本", "第二段文本"])

    document_service.ingest_document_job(doc.id, "job.pdf")

    db_session.expire_all()
    assert db_session.get(Document, doc.id).status == "processed"
    assert db_session.get(Document, doc.id).error_message is None
    # 两张 chunk 记录进了 MySQL
    assert db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count() == 2
    # 两条向量进了 Chroma（按 document_id 精确取，不受其他测试数据影响）
    got = vector_store.collection.get(where={"document_id": doc.id})
    assert len(got["ids"]) == 2


def test_ingest_job_error_marks_failed(db_session, engine, monkeypatch):
    """后台任务失败：状态 → failed，error_message 记录原因（前端能显示）"""
    doc = _setup_doc(db_session)
    _patch_job_deps(monkeypatch, engine, ["文本"], fail=True)

    document_service.ingest_document_job(doc.id, "job.pdf")

    db_session.expire_all()
    failed = db_session.get(Document, doc.id)
    assert failed.status == "failed"
    assert failed.error_message is not None and "embedding" in failed.error_message


def test_delete_document_by_employee_forbidden(client, user_factory, auth_token, db_session):
    """员工删除 → 403"""
    doc = _setup_doc(db_session, status="processed")

    user_factory("E100", role="employee")
    token = auth_token("E100")
    res = client.delete(f"/api/v1/documents/{doc.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_delete_document_by_admin(client, user_factory, auth_token, db_session):
    """管理员删除 → 200，且记录从库里消失"""
    doc = _setup_doc(db_session, status="processed")

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
