from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """集中管理配置（用环境变量可覆盖默认值）"""

    # 数据库连接串：mysql+pymysql://用户:密码@主机:端口/库名
    # 本机 MySQL 已占 3306，Docker 里的 MySQL 映射到宿主机 3307，故用 3307
    DATABASE_URL: str = "mysql+pymysql://root:root@127.0.0.1:3307/copilot"

    # JWT 相关（第4部分会用到）
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1天


settings = Settings()
