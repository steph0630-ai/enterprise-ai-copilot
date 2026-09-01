"""hybrid 重排测试（Day 25）

验证：BM25 关键词重排能让"精确词条"chunk 从向量靠后位次上浮到最前。
评测发现向量只懂语义形似，把含精确 token（IP54/412-8848/600980）的 chunk
排到 #4~#8；BM25 按字面命中把这类 chunk 拉高。
"""

import app.services.retrieval_service as rs
from app.services.keyword import keyword_index, tokenize


# ========== tokenize：短精确 token + 中文 ==========

def test_tokenize_exact_terms():
    """数字/型号这类精确 token 要能整体切出，别被拆散"""
    assert "412-8848" in tokenize("客户电话：412-8848")
    assert "ip54" in tokenize("防护等级 IP54")
    assert "0.3594" in tokenize("每股收益 0.3594")
    assert "600980" in tokenize("公司代码：600980")


def test_tokenize_chinese_unicodes():
    """中文按单字切，让"客户服务电话"这类词能被命中"""
    toks = tokenize("客户服务电话")
    for ch in "客户服务电话":
        assert ch in toks


# ========== 重排融合 ==========

class FakeStore:
    """同时提供 store.search 和 store.collection.get（重排需要语料）"""

    def __init__(self, texts, distances):
        self._texts = texts
        self._dists = distances

    def search(self, query_vec, k=3, where=None):
        n = len(self._texts)
        return {
            "documents": self._texts,
            "metadatas": [{"source": "doc.pdf"} for _ in range(n)],
            "distances": self._dists,
        }

    class _Col:
        def __init__(self, texts):
            self._texts = texts

        def get(self, include="documents", **kw):
            return {"documents": self._texts}

    collection = property(lambda self: FakeStore._Col(self._texts))


def test_rerank_lifts_exact_token(monkeypatch):
    """目标 chunk 向量排第 6（最远），但含查询精确词 8800 → 重排后应升到前部（第 3 名）

    前 2 名被保护冻结（它们更可能是"表格单元格无查询词"的正确 chunk），
    所以目标从 #6 上浮到位置 3，而不是顶掉前二。
    """
    texts = [f"发票报销流程说明第{i}段" for i in range(5)] + ["报销额度具体为 8800元 人民币"]
    distances = [round(0.1 * i, 3) for i in range(6)]

    keyword_index.invalidate()  # 防止别的测试留下的旧索引
    monkeypatch.setattr(rs.retrieval_service.embedding, "embed_query", lambda q: [0.1] * 8)
    monkeypatch.setattr(rs.retrieval_service, "store", FakeStore(texts, distances))

    res = rs.retrieval_service.search("报销额度是多少 8800", k=3)

    assert res[0]["text"] == texts[0]   # 前 1 名仍是向量最近的那个（被保护）
    assert res[2]["text"] == texts[5]   # 精确词条 chunk 上浮到第 3
    assert len(res) == 3
    # 返回结构干净：只有 text/source/distance，没有重排临时键
    assert {"text", "source", "distance"} == set(res[0].keys())


def test_rerank_empty_query_keeps_order(monkeypatch):
    """查询切不出词（纯符号）→ 不崩、保持原向量顺序"""
    texts = [f"正文片段{i}" for i in range(4)]
    distances = [0.2, 0.4, 0.6, 0.8]

    keyword_index.invalidate()
    monkeypatch.setattr(rs.retrieval_service.embedding, "embed_query", lambda q: [0.1] * 8)
    monkeypatch.setattr(rs.retrieval_service, "store", FakeStore(texts, distances))

    res = rs.retrieval_service.search("……", k=2)

    assert [r["text"] for r in res] == texts[:2]  # 原序（向量最近的两个）


def test_rerank_keeps_distance_field(monkeypatch):
    """重排后 distance 仍是原向量距离（相关性过滤要靠它做锚点）"""
    texts = ["甲片段 8800", "乙片段", "丙片段 8800"]
    distances = [0.9, 0.1, 0.8]

    keyword_index.invalidate()
    monkeypatch.setattr(rs.retrieval_service.embedding, "embed_query", lambda q: [0.1] * 8)
    monkeypatch.setattr(rs.retrieval_service, "store", FakeStore(texts, distances))

    res = rs.retrieval_service.search("片段 8800", k=2)
    # 两个含 8800 的都要被保留下 distance 字段
    assert all("distance" in r for r in res)
