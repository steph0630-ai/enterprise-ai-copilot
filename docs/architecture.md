# 系统架构

## 当前运行架构

```text
Browser
  |
  v
Nginx (Vue static files + /api reverse proxy)
  |
  v
FastAPI
  |-- JWT authentication and role checks
  |-- Agent loop
  |    |-- knowledge tool -> RAG
  |    `-- data tool -> MySQL query
  |-- conversation and document APIs
  `-- in-process document background task
       |-- parse text, tables and images
       |-- call embedding / vision APIs
       |-- write chunks to MySQL
       `-- write vectors to Chroma

State:
  MySQL              users, documents, chunks, conversations, messages
  Chroma             document embeddings and metadata
  Local file system  uploaded source files

External AI services:
  SiliconFlow-compatible API  embedding and chat completion
  Zhipu API                   document image understanding
```

## 请求链路

知识问题：

```text
用户问题 -> Agent -> search_knowledge -> Embedding -> Chroma
        -> relevant chunks -> LLM -> answer with sources
```

业务数据问题：

```text
用户问题 -> Agent -> query_data -> MySQL -> structured result -> LLM answer
```

## 当前部署边界

当前 Docker Compose 面向本地开发和单机演示：

- FastAPI 文档任务运行在 Web 进程内，进程退出后未完成任务不会自动恢复。
- Chroma 和上传文件使用本地磁盘，不适合多个后端副本共享。
- 外部模型调用会发送问题、检索片段或文档图片，需要在生产环境补充数据治理。

生产化时优先外置任务和状态，不需要先拆分业务微服务。
