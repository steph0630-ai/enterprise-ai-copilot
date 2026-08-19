from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中管理配置（用环境变量或 .env 文件可覆盖默认值）"""

    # 告诉 pydantic-settings 去读 backend/.env 文件
    # 优先级：环境变量 > .env 文件 > 代码里的默认值
    model_config = SettingsConfigDict(env_file=".env")

    # 数据库连接串：mysql+pymysql://用户:密码@主机:端口/库名
    # 本机 MySQL 已占 3306，Docker 里的 MySQL 映射到宿主机 3307，故用 3307
    DATABASE_URL: str = "mysql+pymysql://root:root@127.0.0.1:3307/copilot"

    # JWT 相关（第4部分会用到）
    # 真实值放 backend/.env（不进 Git），这里留个占位默认值兜底
    SECRET_KEY: str = "dev-only-insecure-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1天

    # Embedding 相关（硅基流动 SiliconFlow 的 OpenAI 兼容接口）
    # 真实 key 放 .env，这里留空兜底
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"  # 中文 embedding 模型

    # LLM 对话相关（同一个硅基流动账号，key 一样）
    # 模型选型教训（Day 7）：Qwen2.5-7B 不支持原生 tool_calls（返回空），
    # Agent 要工具调用必须用 DeepSeek-V3；RAG 用 DeepSeek 效果也更好。
    # temperature 调低防自由发挥
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.siliconflow.cn/v1"
    LLM_MODEL: str = "deepseek-ai/DeepSeek-V3"
    LLM_TEMPERATURE: float = 0.2

    # 上传文件大小上限（Day 18：企业大文件支持）
    # 200MB 字节。nginx 的 client_max_body_size 必须 >= 这个值，否则文件在网关层就被拒
    MAX_DOC_SIZE: int = 200 * 1024 * 1024

    # Day 20：支持的文档扩展名（小写、含点）。
    # 单一来源：上传接口 fail-fast 校验 + parse_document 兜底 共用，扩格式只改这一处。
    # 注意与前端 el-upload 的 accept 属性保持一致。
    SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".docx", ".txt", ".md"}


settings = Settings()
