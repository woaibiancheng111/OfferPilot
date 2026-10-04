# syntax=docker/dockerfile:1

# 依赖单独一层：只有 pyproject.toml / uv.lock 变了才重装，
# 改业务代码只重建上面几行，镜像构建时间基本不受影响。

FROM python:3.12-slim AS deps

# uv 官方镜像里的可执行文件在 / 和 /uvx，拷到 /bin/ 下才能直接当命令用
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev


FROM python:3.12-slim AS runtime

# PYTHONUNBUFFERED：不缓冲 stdout，否则容器日志要等进程结束才吐出来
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=deps /app/.venv /app/.venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# 不用 root 跑。trace 写库失败、agent 报错都不需要特权
RUN useradd --create-home --uid 10001 appuser \
    && chmod +x /usr/local/bin/entrypoint.sh \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 18088

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
