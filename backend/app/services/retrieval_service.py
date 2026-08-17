"""检索服务：把"问题 → 向量 → 检索"这条链路串起来"""

from app.ai.embedding import embedding_service
from app.vectorstore.store import vector_store


class RetrievalService:
    """负责检索：输入一句话，返回最相关的文档片段

    它自己不干活，而是"组合"两个底层能力：
    EmbeddingService（转向量）+ VectorStore（查向量库）。
    """

    def __init__(self) -> None:
        # 直接复用全局单例，不自己 new（避免重复建立客户端/数据库连接）
        self.embedding = embedding_service
        self.store = vector_store

    def search(self, query: str, k: int = 3) -> list[dict]:
        """检索流程：问题 → 向量 → Top K 片段"""
        # 1. 问题转成向量
        query_vec = self.embedding.embed_query(query)

        # 2. 去向量库找最相似的 k 个
        result = self.store.search(query_vec, k=k)

        # 3. 整理成干净的返回结构（调用方不关心 Chroma 的内部格式）
        items = []
        for doc, meta, dist in zip(
            result["documents"], result["metadatas"], result["distances"]
        ):
            items.append(
                {
                    "text": doc,
                    "source": meta.get("source", "未知"),
                    "distance": round(dist, 4),  # 距离越小越相似
                }
            )
        return items


# 模块级单例：整个应用共用一份（OpenAI / Chroma 客户端都能复用，别每次请求都 new）
retrieval_service = RetrievalService()
