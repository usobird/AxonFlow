FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# 复制源码
COPY src/ ./src/
COPY config/ ./config/

# 创建运行时目录
RUN mkdir -p workspace logs

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD autoflow version || exit 1

ENTRYPOINT ["autoflow"]
CMD ["start"]
