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
    # 生成答案的模型：Qwen2.5-7B 便宜够用、中文好；temperature 调低防自由发挥
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.siliconflow.cn/v1"
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    LLM_TEMPERATURE: float = 0.2


settings = Settings()
