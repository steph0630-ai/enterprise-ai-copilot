"""图内容能答出来——三层修复的测试（Day 23）

覆盖：_ingest 图 chunk 打 type=image 标记、store.search 的 where 过滤、
retrieval 图关键词加权、VL 提示词语义化。
（enrich 的 stats 计数已由 test_document_parsers.py 更新过的用例覆盖。）
原则同其余测试：不碰真实向量库/API，全打桩。
"""

from types import SimpleNamespace

from app.services import document_service
from app.services.retrieval_service import retrieval_service
from app.vectorstore.store import VectorStore


# ========== _ingest：图 chunk 打 type=image 标记 ==========

def test_ingest_metadata_type(monkeypatch, db_session):
    """含 [图： 的 chunk 的 metadata 带 type=image，普通 chunk 不带（向后兼容）"""
    captured = {}
    monkeypatch.setattr(
        document_service, "parse_document",
        lambda filename, path: ["正文段落", "某页\n\n[图：报销审批流程图"],
    )
    monkeypatch.setattr(document_service, "extract_pdf_images", lambda path: [])

    def fake_embed(batch):
        return [[0.1] * 8] * len(batch)

    monkeypatch.setattr(document_service.embedding_service, "embed_documents", fake_embed)

    def fake_add(ids, embeddings, documents, metadatas):
        captured["documents"] = documents
        captured["metadatas"] = metadatas

    monkeypatch.setattr(document_service.vector_store, "add", fake_add)

    document_service._ingest(db_session, 999, "a.pdf")

    assert any("[图：" in d for d in captured["documents"]), "测试数据里应真有图 chunk"
    for doc, meta in zip(captured["documents"], captured["metadatas"]):
        if "[图：" in doc:
            assert meta.get("type") == "image", f"图 chunk 应有 type=image: {doc!r}"
        else:
            assert "type" not in meta, f"普通 chunk 不应带 type: {doc!r}"


def test_ingest_metadata_table_type(monkeypatch, db_session):
    """独立表格 chunk 的 metadata 带 type=table。"""
    captured = {}
    monkeypatch.setattr(
        document_service,
        "parse_document",
        lambda filename, path: [
            "正文段落\n\n[表格]\n| 项目 | 金额 |\n| --- | --- |\n| 合计 | 100 |\n[表格结束]"
        ],
    )
    monkeypatch.setattr(document_service, "extract_pdf_images", lambda path: [])
    monkeypatch.setattr(
        document_service.embedding_service,
        "embed_documents",
        lambda batch: [[0.1] * 8] * len(batch),
    )
    monkeypatch.setattr(
        document_service.vector_store,
        "add",
        lambda ids, embeddings, documents, metadatas: captured.update(
            documents=documents, metadatas=metadatas
        ),
    )

    document_service._ingest(db_session, 1000, "a.pdf")

    table_meta = next(
        meta for doc, meta in zip(captured["documents"], captured["metadatas"])
        if doc.startswith("[表格]\n")
    )
    assert table_meta["type"] == "table"


# ========== store.search 的 where 过滤 ==========

def test_store_search_where():
    """where={"type": "image"} 只返回带该标记的 chunk（检索层识别"这是图"的基础）"""
    store = VectorStore(collection_name="test_where_img")  # 独立 collection，不污染主库
    store.add(
        ids=["img1", "txt1"],
        embeddings=[[0.1] * 8, [0.9] * 8],
        documents=["图片内容", "正文内容"],
        metadatas=[{"source": "a.pdf", "type": "image"}, {"source": "a.pdf"}],
    )
    result = store.search([0.1] * 8, k=5, where={"type": "image"})
    assert result["documents"] == ["图片内容"]  # 只有带 type=image 的


# ========== retrieval 图关键词加权 ==========

def test_retrieval_img_keyword_weights(monkeypatch):
    """query 含"图中" → 额外查图 chunk 并排前面、source 标 [图]；不含 → 不查图"""
    calls = []
    monkeypatch.setattr(retrieval_service.embedding, "embed_query", lambda q: [0.1] * 8)

    def fake_store_search(query_vec, k=3, where=None):
        calls.append(where)
        if where == {"type": "image"}:
            return {
                "documents": ["图描述：报销审批四步流程"],
                "metadatas": [{"source": "a.pdf"}],
                "distances": [0.05],
            }
        return {
            "documents": ["正文1：报销制度", "正文2：审批时限"],
            "metadatas": [{"source": "a.pdf"}, {"source": "a.pdf"}],
            "distances": [0.3, 0.4],
        }

    monkeypatch.setattr(retrieval_service.store, "search", fake_store_search)

    # 问"图中" → 图 chunk 排前、source 带 [图] 前缀
    res = retrieval_service.search("图中报销流程是什么", k=3)
    assert calls == [None, {"type": "image"}]  # 先普通，后图
    assert res[0]["text"].startswith("图描述")
    assert res[0]["source"].startswith("[图]")
    assert len(res) == 3  # 合并去重后仍是 3 个

    # 不含图关键词 → 只查一次普通，不插队
    calls.clear()
    res2 = retrieval_service.search("报销限额是多少", k=3)
    assert calls == [None]
    assert res2[0]["text"] == "正文1：报销制度"


# ========== VL 提示词语义化 ==========

def test_vision_prompt_semantic(monkeypatch):
    """提示词要求"主题概括"，不再是"原样列出文字"的流水账（防回退）"""
    from app.ai.vision_service import vision_service

    captured = {}

    def fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="这张图讲报销流程"))]
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    monkeypatch.setattr(vision_service, "client", fake_client)

    desc = vision_service.describe_image(b"\x89PNG-fake", "image/png")

    text_block = captured["messages"][0]["content"][0]["text"]
    assert "主题" in text_block or "概括" in text_block, "提示词应要求语义概括"
    assert "原样列出" not in text_block, "不应再是流水账式提示词"
    assert desc == "这张图讲报销流程"
