# 全局 ARG（必须在首个 FROM 之前声明，供多阶段 FROM 使用）
ARG NODE_BASE_IMAGE=node:22-slim
ARG NGINX_BASE_IMAGE=nginx:1.27-slim

# ── 阶段 1：构建前端 ──
FROM ${NODE_BASE_IMAGE} AS build

WORKDIR /app

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG NPM_REGISTRY=https://registry.npmmirror.com

COPY docker/setup-debian-apt-mirrors.sh /tmp/setup-debian-apt-mirrors.sh
RUN chmod +x /tmp/setup-debian-apt-mirrors.sh && APT_MIRROR=${APT_MIRROR} /tmp/setup-debian-apt-mirrors.sh \
    && rm -f /tmp/setup-debian-apt-mirrors.sh

RUN npm config set registry "${NPM_REGISTRY}"

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build-only

# ── 阶段 2：Nginx 托管静态资源 ──
FROM ${NGINX_BASE_IMAGE}

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn

COPY docker/setup-debian-apt-mirrors.sh /tmp/setup-debian-apt-mirrors.sh
RUN chmod +x /tmp/setup-debian-apt-mirrors.sh && APT_MIRROR=${APT_MIRROR} /tmp/setup-debian-apt-mirrors.sh \
    && rm -f /tmp/setup-debian-apt-mirrors.sh

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
