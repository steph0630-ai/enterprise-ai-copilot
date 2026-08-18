"""向量库：把向量存进 Chroma，并支持"找最相似"的检索"""

from pathlib import Path

import chromadb

# Chroma 数据落盘目录（和上传文件一样放 storage 下——是数据，不是代码）
CHROMA_DIR = Path(__file__).resolve().parent.parent / "storage" / "chroma"


class VectorStore:
    """封装 Chroma 向量库

    两个职责：存（add）和查（search）。
    """

    def __init__(self, collection_name: str = "documents") -> None:
        # PersistentClient：数据写进磁盘，重启不丢
        # （对比 EphemeralClient 是"内存版"，进程一关就没了，只适合临时测试）
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))

        # collection = 一个集合，可理解成一个"表"/一个知识库
        # get_or_create：有就用，没有就新建
        self.collection = self.client.get_or_create_collection(collection_name)

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """批量写入：向量 + 原文 + 元信息（来源）一起存

        ids:        每条记录的唯一 id，如 ["doc1_chunk0", "doc1_chunk1"]
        embeddings: 向量列表（和 documents 一一对应）
        documents:  原文文本列表
        metadatas:  元信息列表，如 [{"source": "报销制度.pdf", "page": 3}, ...]
        """
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete_by_document(self, document_id: int) -> None:
        """删除某个文档的全部向量（Day 14：文档管理）

        Chroma 支持按 metadata 过滤删除：我们入库时每块向量都带了
        {"document_id": ...}，这里按它精确匹配，把该文档的向量一次清空。
        """
        self.collection.delete(where={"document_id": document_id})

    def search(self, query_embedding: list[float], k: int = 3) -> dict:
        """按查询向量找最相似的 k 个，返回干净的 1 层列表"""
        result = self.collection.query(
            query_embeddings=[query_embedding],  # 传列表（可批量查），这里只查 1 个
            n_results=k,
        )

        # query_embeddings 是"一批查询"，结果外头多套了一层列表；只查 1 个就取 [0]
        return {
            "ids": result["ids"][0],
            "documents": result["documents"][0],
            "metadatas": result["metadatas"][0],
            "distances": result["distances"][0],
        }


# 模块级单例：整个应用共用一个向量库实例（Chroma 客户端可复用）
vector_store = VectorStore()
