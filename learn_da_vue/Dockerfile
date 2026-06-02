# Debian 12 (bookworm)
FROM node:22-bookworm-slim AS build

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

FROM nginx:1.27-bookworm

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn

COPY docker/setup-debian-apt-mirrors.sh /tmp/setup-debian-apt-mirrors.sh
RUN chmod +x /tmp/setup-debian-apt-mirrors.sh && APT_MIRROR=${APT_MIRROR} /tmp/setup-debian-apt-mirrors.sh \
    && rm -f /tmp/setup-debian-apt-mirrors.sh

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
