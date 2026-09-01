"""检索服务：把"问题 → 向量 → 检索"这条链路串起来"""

from app.ai.embedding import embedding_service
from app.services.keyword import keyword_index, tokenize  # Day 25：BM25 关键词重排
from app.vectorstore.store import vector_store

# Day 23：这些词说明用户在问"图/图表里的内容"——纯文本检索不懂"图中"这个意图，
# 图描述 chunk 混在文本流里，问"图中X"和"X是什么"对向量相似度没区别。
# 命中这些词 → 额外按 type=image 查图 chunk，把图内容提上来。
IMAGE_QUERY_KEYWORDS = (
    "图中", "图里", "图片", "图表", "流程图", "架构图", "截图", "图示", "示意图",
)

# Day 25 hybrid 重排：把"向量候选池"用 BM25 关键词重排，让精确词条 chunk 上浮。
# 为什么不用"纯排名融合（RRF）"：当 chunk A"向量第1、关键词第6"、chunk B"向量第6、
# 关键词第1"时，RRF 会给两边同样分数，永远拉不动——加权分数（量级）融合才能让
# 强命中的 B 真实上浮。
_BM25_WEIGHT = 1.0       # 关键词分相对向量相似度的权重（越大越让精确命中有话语权）
_BM25_SATURATE = 2.0     # 把 BM25 原始分压进 0~1 的饱和值：分越高越接近 1
_PROTECT_TOP = 2         # 冻结 vector 最信任的前 N 个（往往是"表格单元格里无查询词"的
                         # 正确答案，如 USB-C），其余交给 BM25 重排。若前二被 BM25 一起压下去，
                         # 正确 sparse chunk 会被 8 个弱命中挤没（Day 25 实测教训）。


class RetrievalService:
    """负责检索：输入一句话，返回最相关的文档片段

    它自己不干活，而是"组合"两个底层能力：
    EmbeddingService（转向量）+ VectorStore（查向量库）。
    """

    def __init__(self) -> None:
        # 直接复用全局单例，不自己 new（避免重复建立客户端/数据库连接）
        self.embedding = embedding_service
        self.store = vector_store

    def _query_with_vec(
        self, query_vec: list[float], k: int = 3, where: dict | None = None
    ) -> list[dict]:
        """用现成的向量去查（embedding 只算一次，普通/图检索复用同一个向量）"""
        result = self.store.search(query_vec, k=k, where=where)
        items = []
        for doc, meta, dist in zip(
            result["documents"], result["metadatas"], result["distances"]
        ):
            # 防御：doc 为 None 说明是"幽灵条目"（索引和磁盘不同步，如外部改库后没重启），
            # 直接跳过，别让脏数据进上下文；metadata 也可能是 None，用空 dict 兜底
            if doc is None:
                continue
            items.append(
                {
                    "text": doc,
                    "source": (meta or {}).get("source", "未知"),
                    "distance": round(dist, 4),  # 距离越小越相似
                }
            )
        return items

    def search(self, query: str, k: int = 3) -> list[dict]:
        """检索流程：问题 → 向量 → BM25 重排 → Top K 片段"""
        # 1. 问题转成向量（只算一次）
        query_vec = self.embedding.embed_query(query)

        # 2. 候选池拉大一点（3×k），给 BM25 重排留空间（Day 25）
        pool = max(k * 3, 10)
        items = self._query_with_vec(query_vec, k=pool)

        # 3. BM25 关键词重排：让"精确词条"chunk（如 IP54/412-8848/600980）上浮
        items = self._rerank_by_keyword(query, items)[:k]

        # 4. Day 23：用户明确问"图中/图表/流程图" → 额外查图 chunk，排前面。
        #    老数据没有 type=image 标记 → 图查询为空 → 静默退回普通结果。
        if any(kw in query for kw in IMAGE_QUERY_KEYWORDS):
            img_items = self._query_with_vec(query_vec, k=k, where={"type": "image"})
            if img_items:
                seen = {(it["text"], it["source"]) for it in items}
                # 图 chunk 的 source 标"[图]"前缀——rag 的 context 会显示，模型知道这是图内容
                extra = [
                    dict(it, source=f"[图]{it['source']}")
                    for it in img_items
                    if (it["text"], it["source"]) not in seen
                ]
                items = [*extra, *items][:k]

        return items

    def _rerank_by_keyword(self, query: str, items: list[dict]) -> list[dict]:
        """用 BM25 给向量候选池重排（Day 25）

        对每个候选 chunk 算：向量相似度（1/(1+distance)，距离越小越相关）
        + 权重×BM25 归一化分。按合成分降序排。

        拿不到语料（如测试把 store mock 掉了）或查询切不出词 → 原样返回，
        保证不改动、不崩。
        """
        terms = tokenize(query)
        if not terms or len(items) <= 1:
            return items
        try:
            corpus = self.store.collection.get(include=["documents"])["documents"]
        except Exception:
            return items  # 拿不到语料 → 放弃重排，稳住原序
        if not corpus:
            return items
        keyword_index.build(corpus)

        # 保护制：vector 最信任的前 _PROTECT_TOP 个冻结（不动），
        # 其余（第 3 名往后）交给 BM25 关键词重排——强命中的精确 chunk 上浮，
        # 但不会把"正文里恰好有查询词的弱命中"一起堆到最前面去挤掉正确 sparse chunk。
        # （实测：若不保护前二，8 个中文 unigram 弱命中会把表格单元格里的正确 chunk 顶出 top-8）
        head, tail = items[:_PROTECT_TOP], items[_PROTECT_TOP:]

        for it in tail:
            bm = keyword_index.score(terms, it.get("text") or "")
            bm_norm = bm / (bm + _BM25_SATURATE)              # 0~1，强命中→接近1
            vec_sim = 1.0 / (1.0 + it.get("distance", 0.0))   # L2 距离转相似度
            it["_comb"] = vec_sim + _BM25_WEIGHT * bm_norm

        tail.sort(key=lambda x: x["_comb"], reverse=True)
        for it in tail:
            it.pop("_comb", None)
        return head + tail


# 模块级单例：整个应用共用一份（OpenAI / Chroma 客户端都能复用，别每次请求都 new）
retrieval_service = RetrievalService()
