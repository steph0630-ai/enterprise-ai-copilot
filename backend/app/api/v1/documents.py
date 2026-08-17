from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传文档：保存文件到磁盘 + 写入 documents 表

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

    # 4. Phase 6 新增：把文档变成可检索的向量（解析 → 切分 → 向量化 → 入库）
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
