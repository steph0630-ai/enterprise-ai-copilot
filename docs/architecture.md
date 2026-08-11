# 系统架构

企业智能知识与数据分析 Agent 的整体架构，以及数据在系统各组件间的流动。

## 架构图

```
用户（员工 / 管理员）
        │ 输入自然语言问题
        ▼
   前端（Vue/React）
        │ HTTPS（Nginx 反向代理）
        ▼
   后端：FastAPI（API 入口）
        · 登录鉴权（普通员工 / 管理员 → 权限）
        ▼
   核心：Agent（LLM 大脑 + LangChain）
        · 判断：这个问题该走哪条路？
        ├──────────────┬──────────────┐
        ▼              ▼              ▼
    知识类问题       数据类问题       （无法判断 → 反问用户澄清）
        ▼              ▼
    RAG 检索        SQL Tool
    · 问题→Embedding  · 自然语言→生成 SQL
    · pgvector 检索    · MySQL 执行
        ▼              ▼
   PostgreSQL      MySQL
   (pgvector)     (users/products/orders)
        │              │
        └──────┬───────┘
               ▼
    LLM 整理成自然语言回答
    · 知识类：答案 + 引用来源
    · 数据类：数字 + 结论
```

## 辅助组件

| 组件 | 作用 |
| --- | --- |
| Redis | 缓存 + 对话历史（记住上下文、加速） |
| Celery | 异步处理文档（上传→解析→切片→Embedding→存 pgvector） |

## 主要数据流

### 1. 知识问答（RAG）
1. 用户提问 → FastAPI 鉴权
2. Agent 判断为"知识类"
3. 问题转 Embedding → pgvector 检索相关文档片段
4. LLM 基于片段回答，并给出引用来源

### 2. 业务数据查询（SQL Tool）
1. 用户提问 → FastAPI 鉴权
2. Agent 判断为"数据类"
3. SQL Tool 把自然语言生成 raw SQL
4. **执行前强制拼上权限过滤** `WHERE department = 当前用户部门`（普通员工）
5. MySQL 执行 → LLM 用真实结果回答

### 3. 文档异步处理（Celery）
1. 管理员上传文档
2. FastAPI 立即返回"处理中"（不阻塞用户）
3. Celery 后台解析 → 切片 → 向量化 → 存 pgvector
