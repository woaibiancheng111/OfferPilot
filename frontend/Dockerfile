# syntax=docker/dockerfile:1

# ---- 依赖层 ----
FROM node:22-slim AS deps

WORKDIR /app
# 用 package.json 里 packageManager 钉住的版本，避免本地和 CI 解析出不同依赖树
RUN corepack enable

# pnpm-workspace.yaml 里有 ignoredBuiltDependencies，必须在 install 之前到位，
# 否则 pnpm 会去执行 sharp / unrs-resolver 的构建脚本
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile


# ---- 构建层 ----
FROM node:22-slim AS build

WORKDIR /app
RUN corepack enable

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* 是构建期内联的，不是运行时读环境变量——所以要写成 ARG，
# 在构建阶段就定死。留空表示调同源相对路径，由 nginx 把 /api 转发到后端，
# 这样前后端同域，浏览器不会触发 CORS 预检。
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build


# ---- 运行层 ----
FROM node:22-slim AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN useradd --create-home --uid 10001 appuser

# standalone 目录自带精简过的 node_modules 和 server.js；
# .next/static 和 public 不在里面，要单独拷，否则页面 404、CSS 404
COPY --from=build --chown=appuser:appuser /app/.next/standalone ./
COPY --from=build --chown=appuser:appuser /app/.next/static ./.next/static
COPY --from=build --chown=appuser:appuser /app/public ./public

USER appuser
EXPOSE 3000

CMD ["node", "server.js"]
