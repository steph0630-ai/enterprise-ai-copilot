"""文档接口：上传 / 列表 / 删除（Day 14 起全部要管理员权限）

Day 14 安全修复：上传原本没有任何登录保护——任何人都能往知识库塞文档，
这是"管理端"要做出来的由头。现在三个接口都戴 get_current_admin 帽子。
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),  # Day 14：只有管理员能上传
):
    """上传文档：保存文件到磁盘 + 写入 documents 表 + 向量化入库

    返回：{"filename": "xxx.pdf", "status": "uploaded"}
    """
    # 1. 读文件的二进制内容
    content = await file.read()

    # 2. 保存到磁盘，拿到路径
    file_path = document_service.save_uploaded_file(content, file.filename)

    # 3. 写数据库记录（拿到 doc 对象，里面有数据库生成的自增 id）
    #    knowledge_base_id 先写死为 1（等知识库接口做好再改）
    doc = document_service.create_document_record(
        db=db,
        filename=file.filename,
        file_path=file_path,
        knowledge_base_id=1,
    )

    # 4. 把文档变成可检索的向量（解析 → 切分 → 向量化 → 入库）
    chunk_count = document_service.ingest_document(db, doc.id, file.filename)

    # 5. 标记文档已处理完
    doc.status = "processed"
    db.commit()

    return {
        "filename": file.filename,
        "document_id": doc.id,
        "chunk_count": chunk_count,
        "status": doc.status,
    }


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),  # Day 14：只有管理员能看
):
    """文档列表（管理端用）：每份文档 + 它切出来的 chunk 数

    chunk_count 用一次分组查询取回，避免对每份文档各查一次（N+1 问题）。
    """
    docs = db.query(Document).order_by(Document.id.desc()).all()

    # 一次 GROUP BY 拿到 每个 document_id → chunk 数量
    chunk_counts = dict(
        db.query(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .group_by(DocumentChunk.document_id)
        .all()
    )

    return [
        {
            "id": d.id,
            "filename": d.filename,
            "status": d.status,
            "chunk_count": chunk_counts.get(d.id, 0),
            "created_time": str(d.created_time),
        }
        for d in docs
    ]


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),  # Day 14：只有管理员能删
):
    """删除文档：向量库 + chunks + 磁盘文件 + 记录一起清（见 service 的注释）"""
    doc = document_service.delete_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"document_id": document_id, "filename": doc.filename, "status": "deleted"}
