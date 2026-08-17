"""文档服务：处理文件上传的业务逻辑（保存文件 + 写数据库 + 解析 PDF + 切分）"""

import os
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.document import Document

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
