"""文档服务：处理文件上传的业务逻辑（保存文件 + 写数据库 + 解析 PDF + 切分 + 异步入库）

Day 18 大改造：从"上传时同步入库"变成"上传秒回，后台线程慢慢入库"。
- 大文件（几十 MB 到 200MB）不再把上传请求挂死：请求只负责收文件、建记录，
  真正的解析/向量化挪到 ingest_document_job（FastAPI BackgroundTasks 后台跑）。
- 保存改成流式写盘：边写边数大小，超限即中止，不整文件读进内存。
"""

import os
import threading
from pathlib import Path

from fastapi import HTTPException
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pdfplumber
from sqlalchemy.orm import Session

from app.ai.embedding import embedding_service
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.vectorstore.store import vector_store

# 上传文件的存放目录（相对 backend 根目录）
# 用 Path 对象，自动处理 Windows/Linux 的路径分隔符差异
STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "files"

# 并发保险（Day 18）：向量库 + chunk 表是本地快写，用锁串起来，
# 防止两个上传同时入库时 Chroma/sqlite 撞车。
# 注意：embedding 的 API 调用（慢、网络）放在锁外面，并发不排队。
_ingest_lock = threading.Lock()


def save_uploaded_file(src, filename: str, max_size: int | None = None) -> str:
    """把上传的文件流写到磁盘，返回文件路径（相对 backend 根目录）

    Day 18 改成流式写入：不把整文件读进内存，1MB 一块边写边数字节，
    超上限就删掉半截文件并报 413——企业大文件不能靠"整读进内存"硬撑。

    参数：
        src: 文件对象（Starlette 的 UploadFile.file，读取前已 seek 回开头）
        filename: 原始文件名，如 "合同.pdf"
        max_size: 允许的最大字节数，默认取 settings.MAX_DOC_SIZE（200MB）
    """
    if max_size is None:
        max_size = settings.MAX_DOC_SIZE

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 拼出完整路径，然后分块拷贝
    file_path = STORAGE_DIR / filename
    written = 0
    with open(file_path, "wb") as out:
        while True:
            chunk = src.read(1024 * 1024)  # 每次最多 1MB
            if not chunk:  # 读到头了
                break
            written += len(chunk)
            if written > max_size:  # 超限：删半截文件，别留垃圾
                out.close()
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"文件超过大小上限（{max_size // 1024 // 1024}MB）",
                )
            out.write(chunk)

    # 返回相对路径（相对于 backend 根目录）
    # 用 os.path.relpath 计算，保证可移植
    backend_root = Path(__file__).resolve().parent.parent.parent
    return os.path.relpath(file_path, backend_root)


def create_document_record(
    db: Session,
    filename: str,
    file_path: str,
    knowledge_base_id: int,
    status: str = "uploaded",
) -> Document:
    """往 documents 表插一条记录，返回这个 Document 对象

    Day 18：加 status 参数——上传入口走 "uploading"（还没开始入库），
    老调用不传则保持默认 "uploaded"。
    """
    doc = Document(
        filename=filename,
        file_path=file_path,
        knowledge_base_id=knowledge_base_id,
        status=status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)  # 让 doc 拿到数据库生成的自增 id
    return doc


def parse_pdf(file_path: str) -> list[str]:
    """解析 PDF，返回每一页的文本列表

    为什么用 pdfplumber 而不是 pypdf（Day 18 踩坑）：
    某些 PDF（尤其从 WPS/在线转换器生成的中文 PDF）里，字形→文字的映射表
    ToUnicode 是坏的。pypdf 照表抽，抽出来全是乱码；眼睛看得见、Ctrl+F 搜不到。
    pdfplumber 底层是 pdfminer，会自己重建字形编码，能把这种 PDF 救回来。

    参数：
        file_path: PDF 文件的路径

    返回：
        ["第一页文本", "第二页文本", ...]
    """
    with pdfplumber.open(file_path) as pdf:
        # extract_text() 对没有文字层的页（扫描件）返回 None，用 or "" 兜底
        return [page.extract_text() or "" for page in pdf.pages]


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


def _ingest(db: Session, document_id: int, filename: str, batch_size: int = 32) -> int:
    """把文档变成可检索的向量（解析 → 切分 → 向量化 → 入库）

    这是后台任务真正干的重活。Day 18 改造：
    1. embedding 分批：每批 batch_size 个 chunk 调一次 embed_documents。
       原来把全部 chunk 塞进一个请求，大文件会超 API 的输入上限。
    2. 向量库 + chunk 表的本地写用 _ingest_lock 串行，防并发入库撞车。
    3. 状态流转不归这里管（ingest_document_job 负责），只干"入库"本身。

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

    # 3. 分批向量化 + 入库
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        ids = [f"doc_{document_id}_chunk_{j}" for j in range(i, i + len(batch))]
        metadatas = [
            {"source": filename, "document_id": document_id, "chunk_index": j}
            for j in range(i, i + len(batch))
        ]

        embeddings = embedding_service.embed_documents(batch)  # 慢的 API 调用，放锁外

        with _ingest_lock:  # 本地快写，串行防撞
            vector_store.add(
                ids=ids,
                embeddings=embeddings,
                documents=batch,
                metadatas=metadatas,
            )
            # 把 chunk 也记到 MySQL（document_chunks 表），便于追溯
            for idx, (cid, chunk) in enumerate(zip(ids, batch)):
                db.add(
                    DocumentChunk(
                        document_id=document_id,
                        content=chunk,
                        chunk_index=i + idx,
                        vector_id=cid,
                    )
                )
        db.commit()

    return len(chunks)


def ingest_document_job(document_id: int, filename: str) -> None:
    """后台入库任务：自己开会话跑 _ingest，并负责状态流转（Day 18 异步核心）

    为什么不能复用上传请求的 db？
    FastAPI 的 BackgroundTasks 在响应发完之后才跑，而请求的数据库会话（get_db）
    在响应结束时就关了。所以这里必须自己 SessionLocal() 开一个全新会话，
    干完就关（try/finally），绝不泄漏连接。

    status 流转：uploading → processing → processed（成功）
                              ↘ failed + error_message（异常原因存起来，前端可查）
    """
    db = SessionLocal()
    try:
        db.query(Document).filter(Document.id == document_id).update(
            {"status": "processing"}
        )
        db.commit()

        _ingest(db, document_id, filename)

        db.query(Document).filter(Document.id == document_id).update(
            {"status": "processed", "error_message": None}
        )
        db.commit()
    except Exception as e:
        # 任何一步挂了：先回滚失败事务，再标记 failed + 记原因（截断到列宽）
        db.rollback()
        db.query(Document).filter(Document.id == document_id).update(
            {"status": "failed", "error_message": str(e)[:500]}
        )
        db.commit()
    finally:
        db.close()


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
