#!/bin/sh
# 容器启动顺序：挡住会一路带到生产的错误 → 等数据库 → 迁移 → 起服务。
set -e

# ---- 1. 配错了就别起 ----
# 这几条都是"看起来能起来、实际上把错误带进生产"的坑，启动这一步直接拦掉。
#
# 占位符：postgres 对密码只要求"非空"，不校验强度。实测把模板里的
# 「改成你自己的强密码」原样给它，库能正常起来——忘了改模板的话，
# 生产会带着一个写死在公开仓库里的密码上线，而且看起来一切正常。
#
# 没配 / 指向 localhost：config.py 里 DATABASE_URL 有个本地开发的默认值
# （localhost:55432，对应开发版 compose 的端口映射）。生产漏配时它会静默
# 兜底，然后表现为"连了 60 秒连不上数据库"，真正的原因被完全掩盖。
case "${DATABASE_URL:-}" in
  *改成你自己的强密码*|*"YOUR_PASSWORD"*|*"changeme"*)
    echo "错误：DATABASE_URL 里的密码还是模板占位符。" >&2
    echo "     请改 deploy/.env.production 里的 POSTGRES_PASSWORD 和 DATABASE_URL 两行，" >&2
    echo "     两处要填成同一个值。" >&2
    exit 1
    ;;
  "")
    echo "错误：没有设置 DATABASE_URL。" >&2
    echo "     它不会报错退出，而是会静默用 app/config.py 里的本地开发默认值" >&2
    echo "     （localhost:55432），然后表现为连不上数据库。" >&2
    echo "     请在 deploy/.env.production 里补上 DATABASE_URL。" >&2
    exit 1
    ;;
  *@localhost:*|*"@127.0.0.1:"*)
    echo "错误：DATABASE_URL 指向了 localhost（$DATABASE_URL）。" >&2
    echo "     compose 里各服务要用服务名互访，后端应该连 postgres:5432。" >&2
    exit 1
    ;;
esac

# ---- 2. 等数据库能连上 ----
# 只探 TCP 端口，不发 SQL。目的是把「数据库还没起来」和「迁移脚本写错了」
# 这两种失败区分开：前者重试，后者立刻报错。
# 前一种确实会发生——compose 的 depends_on 已经用 service_healthy 等过一轮，
# 但首次部署 postgres 要跑 initdb，pg_isready 可能在建库途中就报就绪。
db_reachable() {
    python -c "
import os, socket, sys, urllib.parse
u = urllib.parse.urlparse(os.environ['DATABASE_URL'])
try:
    socket.create_connection((u.hostname, u.port or 5432), timeout=2).close()
except OSError:
    sys.exit(1)
" >/dev/null 2>&1
}

echo '==> 等待数据库就绪'
attempt=1
max_attempts=20
until db_reachable; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "错误：等了 $((max_attempts * 3)) 秒数据库端口仍未打开。" >&2
        echo "     先看 postgres 状态：docker compose -f docker-compose.prod.yml ps" >&2
        echo "     再确认 .env.production 里 POSTGRES_PASSWORD 和 DATABASE_URL 是否一致。" >&2
        exit 1
    fi
    printf '    还没就绪，3 秒后重试（第 %s/%s 次）\n' "$attempt" "$max_attempts"
    sleep 3
    attempt=$((attempt + 1))
done
echo '==> 数据库已就绪'

# ---- 3. 迁移 ----
# 放这里而不是让运维手动跑：单机部署每次发版都会重建容器，忘了执行的话
# 服务起来了但新表不存在，报错落在第一个真实请求上，比启动失败更难查。
# alembic 自己记版本，重复执行是幂等的。
# 上面已经确认端口通了，所以这里失败就一定是迁移本身的问题，直接暴露。
echo '==> 应用数据库迁移'
alembic upgrade head

# ---- 4. 起服务 ----
# exec：让 uvicorn 变成 PID 1，收到 SIGTERM 直接退出，不用等 shell 转发，
# docker stop 才不会每次都等满 10 秒超时才被 SIGKILL
echo '==> 启动 uvicorn'
exec uvicorn app.main:app --host 0.0.0.0 --port 18088 --proxy-headers
