"""检索服务：把"问题 → 向量 → 检索"这条链路串起来"""

from app.ai.embedding import embedding_service
from app.vectorstore.store import vector_store

# Day 23：这些词说明用户在问"图/图表里的内容"——纯文本检索不懂"图中"这个意图，
# 图描述 chunk 混在文本流里，问"图中X"和"X是什么"对向量相似度没区别。
# 命中这些词 → 额外按 type=image 查图 chunk，把图内容提上来。
IMAGE_QUERY_KEYWORDS = (
    "图中", "图里", "图片", "图表", "流程图", "架构图", "截图", "图示", "示意图",
)


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
        """检索流程：问题 → 向量 → Top K 片段"""
        # 1. 问题转成向量（只算一次）
        query_vec = self.embedding.embed_query(query)

        # 2. 普通检索
        items = self._query_with_vec(query_vec, k=k)

        # 3. Day 23：用户明确问"图中/图表/流程图" → 额外查图 chunk，排前面。
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


# 模块级单例：整个应用共用一份（OpenAI / Chroma 客户端都能复用，别每次请求都 new）
retrieval_service = RetrievalService()
