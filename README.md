# Enterprise AI Copilot

**企业智能知识与数据分析 Agent**

企业内部存在大量非结构化知识文档和业务数据，员工需要花费大量时间查询资料和分析数据。

本项目通过 **LLM Agent 技术**，帮助员工通过**自然语言**完成知识检索和业务分析。

---

## 用户角色

| 角色 | 权限 |
| --- | --- |
| 普通员工 | 查询知识、查询自己部门数据 |
| 管理员 | 管理知识库、查看全部数据 |

## 核心功能

1. 企业知识库问答（RAG）
2. 业务数据库查询（SQL Tool）
3. AI Agent 工具调用
4. 用户权限管理
5. 对话历史保存
6. 文档异步处理

## 技术栈

### Backend
- FastAPI

### AI
- LangChain
- OpenAI API
- Embedding
- RAG

### Database
- MySQL
- PostgreSQL + pgvector
- Redis

### Infrastructure
- Docker
- Nginx
- Celery

## 文档

- [系统架构](./docs/architecture.md)
- [数据库设计](./docs/database.md)
- [Agent 流程](./docs/agent-flow.md)