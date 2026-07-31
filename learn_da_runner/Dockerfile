# Runner service image — hosts the HTTP API and Docker SDK only.
# The actual code execution happens inside sandbox containers (Dockerfile.sandbox).
ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

COPY learn_da/docker/setup-debian-apt-mirrors.sh /tmp/setup-debian-apt-mirrors.sh
RUN chmod +x /tmp/setup-debian-apt-mirrors.sh && APT_MIRROR=${APT_MIRROR} /tmp/setup-debian-apt-mirrors.sh \
    && rm -f /tmp/setup-debian-apt-mirrors.sh

COPY learn_da_runner/pyproject.toml /app/pyproject.toml
RUN pip install --index-url "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" .

COPY learn_da_runner/runner /app/runner

# Non-root: create a runner user, but the runner needs Docker socket access.
# Docker socket permissions are managed by the host mount.
RUN useradd -r -u 65532 -g 0 runner && chown -R runner:0 /app
USER 65532:0

EXPOSE 8080

CMD ["uvicorn", "runner.main:app", "--host", "0.0.0.0", "--port", "8080"]
