# 数据库设计

## MySQL

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `users` | 登录身份与权限 | `employee_no`、`hashed_password`、`role`、`department` |
| `knowledge_bases` | 知识库基本信息 | `name`、`owner_id` |
| `documents` | 上传文件与处理状态 | `knowledge_base_id`、`filename`、`file_path`、`status` |
| `document_chunks` | 可追溯的文本片段 | `document_id`、`content`、`chunk_index`、`vector_id` |
| `orders` | 数据查询工具的演示业务表 | `department`、`amount`、`created_at` |
| `conversations` | 用户会话 | `user_id`、`title`、`updated_at` |
| `messages` | 会话消息 | `conversation_id`、`role`、`content` |

数据库结构由 SQLAlchemy 模型描述，历史变更通过 Alembic 迁移记录。

## Chroma

Chroma 保存文档 chunk 的向量、原文和检索元数据：

```text
id            doc_<document_id>_chunk_<index>
document      chunk text
embedding     embedding vector
metadata      source, document_id, chunk_index, optional type=image
```

MySQL 的 `document_chunks.vector_id` 用于把关系数据与 Chroma 条目对应起来。

## 本地文件存储

上传的原始文件保存在 `backend/app/storage/files/`。该目录和 Chroma 数据均属于运行时数据，不提交到 Git。

## 当前约束

- 当前知识库上传固定使用 `knowledge_base_id=1`，尚未完成多知识库 ACL。
- 部分模型字段仅在注释中表达关联，后续需要补真实外键和数据库约束。
- 本地文件与 Chroma/MySQL 之间不是同一个事务，需要后续增加失败补偿和一致性检查。
