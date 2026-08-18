"""文档服务：处理文件上传的业务逻辑（保存文件 + 写数据库 + 解析 PDF + 切分）"""

import os
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.ai.embedding import embedding_service
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.vectorstore.store import vector_store

# 上传文件的存放目录（相对 backend 根目录）
# 用 Path 对象，自动处理 Windows/Linux 的路径分隔符差异
STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "files"


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    """把文件字节保存到磁盘，返回文件路径（相对 backend 根目录）

    参数：
        file_content: 文件的二进制内容（await file.read() 得到）
        filename: 原始文件名，如 "合同.pdf"

    返回：
        相对路径字符串，如 "app/storage/files/合同.pdf"
    """
    # 1. 确保目录存在（不存在就创建）
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 2. 拼出完整路径
    file_path = STORAGE_DIR / filename

    # 3. 写入文件（"wb" = 二进制写）
    with open(file_path, "wb") as f:
        f.write(file_content)

    # 4. 返回相对路径（相对于 backend 根目录）
    #    用 os.path.relpath 计算，保证可移植
    backend_root = Path(__file__).resolve().parent.parent.parent
    return os.path.relpath(file_path, backend_root)


def create_document_record(
    db: Session,
    filename: str,
    file_path: str,
    knowledge_base_id: int,
) -> Document:
    """往 documents 表插一条记录，返回这个 Document 对象"""
    doc = Document(
        filename=filename,
        file_path=file_path,
        knowledge_base_id=knowledge_base_id,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)  # 让 doc 拿到数据库生成的自增 id
    return doc


def parse_pdf(file_path: str) -> list[str]:
    """解析 PDF，返回每一页的文本列表

    参数：
        file_path: PDF 文件的路径

    返回：
        ["第一页文本", "第二页文本", ...]
    """
    reader = PdfReader(file_path)  # 打开 PDF

    pages_text = []
    for page in reader.pages:  # 遍历每一页
        text = page.extract_text()  # 提取这一页的文字
        pages_text.append(text)

    return pages_text


def split_text(pages_text: list[str], chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """把多页文本切成 chunk

    参数：
        pages_text: 每一页的文本列表，如 ["第一页...", "第二页..."]
        chunk_size: 每个 chunk 最多多少字符
        chunk_overlap: 相邻 chunk 重叠多少字符

    返回：
        chunk 文本列表，如 ["chunk1...", "chunk2...", ...]
    """
    # 1. 先把多页合并成一大段
    full_text = "\n".join(pages_text)

    # 2. 用 RecursiveCharacterTextSplitter 切分
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    # 3. 切分，返回 chunk 列表
    chunks = splitter.split_text(full_text)
    return chunks


def ingest_document(db: Session, document_id: int, filename: str) -> int:
    """上传后的完整处理：解析 → 切分 → 向量化 → 存入向量库 + chunks 表

    这是"入库"链路的核心（Phase 6）：
    把一份 PDF 变成向量库里可被检索的一堆 chunk。

    返回：切出来的 chunk 数量
    """
    # 1. 解析 PDF（用绝对路径，不依赖运行时的工作目录）
    abs_path = STORAGE_DIR / filename
    pages_text = parse_pdf(str(abs_path))

    # 2. 切块
    chunks = split_text(pages_text)

    # 空文档（如扫描件没有文本层）就跳过向量化
    if not chunks:
        return 0

    # 3. 批量向量化（一次 API 请求搞定所有 chunk，省往返）
    embeddings = embedding_service.embed_documents(chunks)

    # 4. 存进向量库（Chroma），带上来源元信息（可追溯）
    ids = [f"doc_{document_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {"source": filename, "document_id": document_id, "chunk_index": i}
        for i in range(len(chunks))
    ]
    vector_store.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )

    # 5. 把 chunk 也记到 MySQL（document_chunks 表），便于追溯
    for i, chunk in enumerate(chunks):
        db.add(
            DocumentChunk(
                document_id=document_id,
                content=chunk,
                chunk_index=i,
                vector_id=ids[i],
            )
        )
    db.commit()

    return len(chunks)


def delete_document(db: Session, document_id: int) -> Document | None:
    """删除一个文档（Day 14 文档管理）

    顺序很关键：先清"引用"（向量库、chunks 表），再删"主体"（记录、文件）。
    从外向里删，避免删了主体还留着悬空的向量/chunk。

    返回被删的 Document；不存在返回 None。
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc is None:
        return None

    # 1. 清向量库：按 metadata 里的 document_id 过滤删除
    vector_store.delete_by_document(document_id)

    # 2. 清 chunks 表
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()

    # 3. 删磁盘文件（file_path 是相对 backend 根目录存的，转绝对路径）
    backend_root = Path(__file__).resolve().parent.parent.parent
    abs_path = backend_root / doc.file_path
    if abs_path.exists():
        abs_path.unlink()

    # 4. 删记录
    db.delete(doc)
    db.commit()
    return doc
