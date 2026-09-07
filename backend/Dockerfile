# 后端镜像（Day 17 重写）
# 基础镜像：官方 Python 3.13 精简版
FROM python:3.13-slim

# 工作目录
WORKDIR /app

# 先复制依赖清单再装（利用 Docker 缓存，改代码不用重装依赖）
# 加国内 PyPI 源，避免 build 卡在拉 PyPI 国外依赖上。用阿里云（覆盖全、同步及时；
# 清华/中科大曾缺 requirements 里的 alembic==1.19.1 导致 build 失败）。
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple -r requirements.txt

# 复制应用代码（.dockerignore 会挡住 venv/.env/storage 等）
COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini create_tables.py docker-entrypoint.py ./

# 入口：等数据库就绪 → 建表 → alembic stamp → 种子 → 起 uvicorn
# 用 python 脚本而不是 shell 脚本，避免 Windows/Linux 换行符问题
CMD ["python", "docker-entrypoint.py"]
