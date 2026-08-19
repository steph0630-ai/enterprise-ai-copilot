"""文档接口：上传 / 列表 / 删除（Day 14 起全部要管理员权限）

Day 14 安全修复：上传原本没有任何登录保护——任何人都能往知识库塞文档，
这是"管理端"要做出来的由头。现在三个接口都戴 get_current_admin 帽子。
Day 18 异步化：上传只负责"收文件 + 建记录 + 排队后台入库"，秒回。
"""

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,  # Day 18：FastAPI 注入的后台任务队列
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),  # Day 14：只有管理员能上传
):
    """上传文档：流式落盘 + 建记录，然后排队后台入库，**立即返回**

    为什么改成异步（Day 18）：
    大文件入库 = 解析 + 切分 + 逐批调 embedding API，可能要几十秒到几分钟。
    让上传请求一直挂着等它跑完，浏览器会超时。所以：
    1. 这里只负责把文件存下来、在 documents 表建一条 status="uploading" 的记录；
    2. 真正的入库（ingest_document_job）交给 FastAPI BackgroundTasks，
       等响应返回之后在后台线程池里跑，状态会自己从 uploading → processed/failed。

    返回：{"filename": "xxx.pdf", "document_id": 3, "status": "uploading"}
    """
    # Day 20：fail-fast 白名单校验。非支持格式【不写盘】直接 400，
    # 修复"不支持的格式传上去秒回成功、后台才翻车"的体验问题。
    # safe_name 全程贯通（写盘/DB/后台任务）：sanitize 剥掉路径成分防穿越，
    # 读文件（_ingest 里 STORAGE_DIR / filename）与写文件落在同一路径，两端闭合。
    safe_name = document_service.sanitize_filename(file.filename or "")
    ext = document_service.get_extension(file.filename)
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的文件类型：{ext or '（无扩展名）'}，"
                f"仅支持 {' / '.join(sorted(settings.SUPPORTED_EXTENSIONS))}"
            ),
        )

    # 1. 流式写盘 + 体积校验（超 200MB 中途就 413，不会把大文件读进内存）
    file.file.seek(0)  # 确保从文件开头读（多部分解析可能移动了指针）
    file_path = document_service.save_uploaded_file(file.file, safe_name)

    # 2. 写数据库记录（status="uploading"，等待后台任务接管）
    #    knowledge_base_id 先写死为 1（等知识库接口做好再改）
    doc = document_service.create_document_record(
        db=db,
        filename=safe_name,
        file_path=file_path,
        knowledge_base_id=1,
        status="uploading",
    )

    # 3. 排队后台入库（响应返回后才执行）
    background_tasks.add_task(
        document_service.ingest_document_job, doc.id, safe_name
    )

    return {
        "filename": file.filename,
        "document_id": doc.id,
        "status": "uploading",  # 不再是 "processed"——入库还在后台跑
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
            "error_message": d.error_message,  # Day 18：失败原因，前端 tooltip 显示
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
