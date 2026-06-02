# Debian 12 (bookworm)
FROM python:3.12-bookworm-slim

WORKDIR /app

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    UV_INDEX_URL=${PIP_INDEX_URL}

COPY docker/setup-debian-apt-mirrors.sh /tmp/setup-debian-apt-mirrors.sh
RUN chmod +x /tmp/setup-debian-apt-mirrors.sh && APT_MIRROR=${APT_MIRROR} /tmp/setup-debian-apt-mirrors.sh \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/* /tmp/setup-debian-apt-mirrors.sh

RUN useradd --create-home --shell /bin/bash appuser

COPY pyproject.toml uv.lock* ./

RUN pip install --upgrade pip -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" && \
    pip install uv -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" && \
    uv pip install --system -i "${PIP_INDEX_URL}" -e .

COPY . .

RUN mkdir -p /app/logs /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
