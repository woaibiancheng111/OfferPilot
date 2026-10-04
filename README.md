# OfferPilot

求职 Agent + 自研观测评测平台。完整方案见 [`docs/OfferPilot项目方案.md`](docs/OfferPilot项目方案.md)（v2，含修订记录）。

当前进度：**第 3 周进行中**。已完成手写 agent loop、双厂商模型抽象层、Trace SDK、落库前脱敏、prompt 内容 hash 版本号、JD 解析 Agent、多 Agent 模拟面试（规划/提问/评估）、SSE 流式输出（含断线续传）、Next.js 面试工作台与 Trace 看板、130 个测试全绿、CI 与生产部署编排。

## 快速开始

需要 Python 3.12、[uv](https://docs.astral.sh/uv/)、Node 20+ 和 Docker。

```bash
# 1. 启动 PostgreSQL（端口 55432）和 Redis（端口 56379）
docker compose up -d

# 2. 后端：安装依赖并建表
cd backend
uv sync
cp .env.example .env        # 填入 ANTHROPIC_API_KEY 或 OPENAI_API_KEY
uv run alembic upgrade head

# 3. 跑测试（不需要 API key，也不需要数据库）
uv run pytest

# 4. 启动后端
uv run uvicorn app.main:app --reload --port 18088
```

另开一个终端起前端：

```bash
cd frontend
pnpm install
pnpm dev                    # http://localhost:3000
```

后端文档在 http://localhost:18088/docs，前端在 http://localhost:3000。

> **开发时不要把 dev server 的日志重定向进 `frontend/` 目录**——Next.js 的文件
> 监听会盯着那里，日志每写一行就触发一次 HMR，页面反复重挂载，表现为
> 自动拉数据的页面永远停在「加载中」。日志请写到项目外面。

## 切换模型

只改 `.env`，不用动代码：

```bash
# 切到 OpenAI
LLM_VENDOR=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# 切回 Claude
LLM_VENDOR=anthropic
LLM_MODEL=claude-opus-5
ANTHROPIC_API_KEY=sk-ant-...
```

接第三方中转站时再补一个 `OPENAI_BASE_URL` 即可。模型名没有白名单，填你实际能调通的那个。

### 第三方中转：阿里云百炼 DashScope（已实测跑通）

百炼提供 OpenAI 兼容端点，qwen 系列直接用上面这套配置，一行代码都不用改：

```bash
LLM_VENDOR=openai
LLM_MODEL=qwen-max            # 也可用 qwen-plus / qwen-turbo
OPENAI_API_KEY=<你的 DASHSCOPE_API_KEY>
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_LEGACY_MAX_TOKENS=false
LLM_ENABLE_PROMPT_CACHE=false  # 第三方端点一般不支持 prompt_cache_key
```

已验证：`qwen-max` / `qwen-plus` / `qwen-turbo` 都支持**工具调用**（JD 解析依赖它），
`max_completion_tokens` 和 `max_tokens` 两种写法都接受。

## 试一下

```bash
# 让演示 Agent 调用工具
curl -X POST localhost:18088/api/agent/demo \
  -H 'Content-Type: application/json' \
  -d '{"message": "(37 * 91) + 2 ** 12 等于多少？现在上海几点？"}'
# 返回 {"text": ..., "trace_id": "...", "cost_usd": ...}

# 查看这次调用的完整 trace 树
curl localhost:18088/api/traces/<trace_id>
```

## 目录结构

```
offerpilot/
├── backend/          # FastAPI：Agent、Trace SDK、评测引擎
├── frontend/         # Next.js：面试工作台 + Trace 看板
├── deploy/           # 生产部署：nginx 配置 + 环境变量模板
├── docs/             # 项目方案 v2
├── docker-compose.yml         # 本地开发：只起 pg 和 redis
├── docker-compose.prod.yml    # 生产：五个服务全套
├── .github/workflows/ci.yml
└── README.md
```

## 前端

`frontend/` 用 Next.js（App Router）+ TypeScript + Tailwind。

```
frontend/src/
├── app/
│   ├── page.tsx                 面试工作台：JD 解析 → 规划 → 一问一答 → 逐轮评估
│   └── traces/
│       ├── page.tsx             trace 列表（分页）
│       └── [id]/TraceView.tsx   span 树 + 瀑布条 + 评估卡片
├── components/ui.tsx            基础组件
└── lib/
    ├── api.ts                   带类型的 API 客户端
    └── types.ts                 与后端 schema 对应的类型
```

面试工作台是测试主入口：粘贴 JD → 解析 → 可选填简历 → 开始面试 → 逐轮答题。
每轮下面显示四维评分和"下一步建议"，点 trace 链接能看到这一轮底下的
agent / llm / tool 调用树。

## 后端目录

```
backend/
├── app/
│   ├── agents/
│   │   ├── loop.py          # 手写的 agent loop
│   │   ├── prompts/         # prompt 模板与内容 hash 版本号
│   │   ├── jd_parser.py     # JD 解析 Agent（结构化输出 + 失败重试）
│   │   ├── planner.py       # 规划 Agent → 面试大纲
│   │   ├── interviewer.py   # 面试官 Agent（纯文本，为 SSE 流式预留）
│   │   ├── evaluator.py     # 评估 Agent → 多维打分 + 下一步建议
│   │   └── demo.py          # 演示 Agent（脚手架，用完即删）
│   ├── services/            # 用例层：开 trace、编排 agent、组装结果
│   ├── schemas/             # 领域模型（同时是 LLM 结构化输出的契约）
│   ├── schemas/jd.py        # JDAnalysis：LLM 结构化输出的 Pydantic 模型
│   ├── llm/
│   │   ├── base.py          # 与厂商无关的消息格式和 LLMClient 协议
│   │   ├── errors.py        # 与厂商无关的异常
│   │   ├── factory.py       # 按 .env 构造客户端
│   │   ├── anthropic_provider.py  # Claude 适配器
│   │   └── openai_provider.py     # OpenAI 兼容端点适配器
│   ├── security/redact.py   # 落库前脱敏（手机号/邮箱/身份证/学号/银行卡）
│   ├── tools/registry.py    # 工具注册中心：签名 → JSON Schema + 参数校验
│   ├── tracing/             # 自研 Trace SDK
│   │   ├── tracer.py        # contextvars 传递上下文、@trace_span 装饰器
│   │   ├── exporter.py      # 异步批量导出（落库前统一脱敏）
│   │   └── serialize.py     # 安全序列化 + 截断
│   ├── db/                  # SQLAlchemy 模型、trace 写库
│   ├── api/                 # FastAPI 路由
│   ├── config.py
│   └── main.py
├── alembic/                 # 数据库迁移
└── tests/                   # 用假 LLM 和 SQLite 测试，离线就能跑
```

## 设计要点

**Agent loop**（`app/agents/loop.py`）
- 同一轮的多个工具调用用 `asyncio.gather` 并发执行，所有结果放在同一条消息里回传
- 工具报错、超时、参数校验失败，都作为 `is_error` 结果返回给模型，让它自行修正，循环不会中断
- 达到最大步数后，以 `tool_choice=none` 再调用一次模型，强制它收尾
- 输出因 `max_tokens` 被截断时，不执行其中可能不完整的工具调用
- 历史只追加不修改；Claude 返回的原始内容块（包括 thinking 块）原样回传

**Trace SDK**（`app/tracing/`）
- `contextvars` 保证并发请求之间的 span 互不串线（见 `test_concurrent_requests_do_not_mix_spans`）
- 业务协程只做一次入队，写库由后台任务批量完成；队列满或写库失败时丢弃数据并计数，绝不拖慢主流程
- 涉及隐私的函数可以用 `capture_input=False` 关闭记录

**隐私脱敏**（`app/security/redact.py`）
- 脱敏挂在 `BatchExporter.enqueue()` 上，也就是 trace 唯一的落库入口，业务代码绕不过去
- 覆盖手机号、邮箱、身份证、学号、银行卡；规则按顺序生效，避免 11 位手机号被学号规则误伤
- 脱敏后保留内容指纹（`attributes.input_hash`），能回答"这条敏感输入是不是又出现了"，但不存原文
- 导出器上有 `redacted_spans` 计数器，这个数突然上涨说明线上出现了新的敏感字段
- **已知局限**：正则只能覆盖格式化明确的标识符，家庭住址、公司内部代号这类自由文本匹配不到

**分层**
- `api/`：HTTP 边界，只做校验入参 → 调用例 → 映射状态码。不含业务逻辑，不碰 tracer
- `services/`：用例层。开 trace、串 agent、组装结果、收敛业务异常
- `agents/`：单个 agent 的能力。prompt + loop，不认识 HTTP，不显式开 trace
- trace 归用例层的理由：它表示"一次业务操作"。放 API 层，CLI 调用就没 trace；放 agent 层，同一个 agent 被两个用例复用会开两条

**多 Agent 模拟面试**（`agents/planner.py` / `interviewer.py` / `evaluator.py` + `services/interview_service.py`）
- **验收标准是评估结果真的改变下一题**。测试里直接断言"同一条历史，只因为评估不同，面试官收到的 prompt 就不同"——否则三个 agent 只是三次 LLM 调用
- 评估连续建议留在当前知识点 2 次后强制换题。真实跑出来发现候选人一直接受差时，评估会一直建议加难度，死磕一个点不换
- 面试官用纯文本不用工具：它要留给 SSE 流式推，工具调用要等参数校验完才结束响应，两者不能共存于一次响应
- 对话历史从已存轮次重建，不额外维护一份可能不一致的副本
- 当前每轮 9–11s（评估两次往返 + 提问一次），这是串行基线

**结构化输出**（`ToolRegistry.submit()`）
- 把 Pydantic 模型直接注册成"提交结果"的工具，模型的 JSON Schema 就是工具的 `input_schema`
- 参数由 Pydantic 校验，失败时**具体是哪个字段、期望什么、模型实际填了什么**会作为 `is_error` 回给模型
- 重试机制复用的是 agent loop 已有的错误自修正，没有另写一套
- 模型用文字回答却没调用提交工具时，外层追问一次；仍不提交才报错
- JD 原文用 `<job_description>` 标签包裹，system 里声明标签内是数据不是指令（注入防护）

**模型适配**（`app/llm/`）
- 换厂商、换模型只改 `.env` 里的 `LLM_VENDOR` / `LLM_MODEL`，代码不动
- 业务层只认识 `app/llm/base.py` 里的消息格式和 `LLMClient` 协议，不 import 任何厂商 SDK
- 厂商异常在 provider 层翻译成中立异常（`errors.py`），API 层据此映射 HTTP 状态码，不认 `anthropic.AuthenticationError` 这类具体类型
- 两家的协议差异（system 的位置、工具结果的消息形态、工具参数的 JSON 字符串）都在各自 provider 里转换
- **只统计 token，不折算金额**：可能接第三方中转，模型名和单价不在我们控制内，写死的价目表只会持续给出错误数字。要换算成钱，乘自己的单价即可
- 代码里不校验模型名，用哪家、用哪个模型完全由 `.env` 决定
- `prompt_cache_key` 由 system 提示自动派生，保证同一套提示稳定命中缓存

**Prompt 版本号**（`app/agents/prompts/`）
- 版本号是 `sha256(prompt)[:8]`，`run_agent` 在没传 `prompt_version` 时自动算
- 没有手写版本号这个选项，也就没有"改了 prompt 忘了改版本号"导致前后对比悄悄失效的问题
- agent span 和它下面的 llm span 都带版本号，回归时能按版本分组

## 部署

服务器已 ICP 备案，域名就位，上线没有等待期。整套编排是 `docker-compose.prod.yml`：
后端、前端、Nginx、Postgres、Redis 五个服务，应用之间走 compose 内网，
数据库不映射到宿主机端口。

```bash
# 1. 填生产环境变量
cp deploy/.env.production.example deploy/.env.production
#   至少要改 POSTGRES_PASSWORD、LLM_VENDOR、LLM_MODEL 和 API key

# 2. 先在 nginx.conf 里把 offerpilot.example.com 换成真实域名（共 3 处）

# 3. 签证书。nginx 此刻还没证书，起不来，所以先单独跑 certbot：
docker compose -f docker-compose.prod.yml run --rm --entrypoint "" \
  certbot certonly --standalone -d <你的域名> --agree-tos -m <你的邮箱>

# 4. 起全套
docker compose -f docker-compose.prod.yml up -d --build

# 5. 看日志
docker compose -f docker-compose.prod.yml logs -f backend
```

数据库迁移由 `backend/docker/entrypoint.sh` 在启动时执行（`alembic upgrade head`），
不用手动跑。alembic 记版本，重复执行是幂等的。

### Nginx 上最容易踩的坑

`deploy/nginx/offerpilot.conf` 里 `/api/` 那段的 `proxy_buffering off` 是
**流式能不能用的分水岭**。开着缓冲的话，SSE 会被攒成一次性返回——前端
逐字上屏的效果完全看不出来，看上去就是"没做流式"。同一段里还有三处配套：
`gzip off`（压缩会把事件攒在缓冲区里等凑够）、`proxy_read_timeout 3600s`
（默认 60s 会把还在评估的一轮掐断）、`Connection ""`（置空而非 close，
不干扰上游 keepalive）。

改完配置先验证再重启：

```bash
docker compose -f docker-compose.prod.yml run --rm nginx nginx -t
```

> ⚠️ 配置文件要存成 **UTF-8 无 BOM**。nginx 读到 BOM 会报
> `unknown directive "﻿#"`，而且报错信息里的那个字符很难肉眼分辨。
> 从 Windows 编辑器另存的配置文件最容易带上 BOM。

## CI

`.github/workflows/ci.yml`：push 到 main 和所有 PR 都会跑两个 job——
后端 `ruff check` + `ruff format --check` + `pytest`，前端 `next build`
（里面会跑 tsc，类型错误会在这里挂掉）。都不需要 API key，也不需要数据库：
测试用假 LLM + SQLite。

ruff 先于 pytest 执行，因为它只要几秒，风格问题没必要等测试跑完两分钟才报。

## 下一步

**第 3 周**

- [x] JD 解析 Agent（结构化输出 + 校验失败自动重试）
- [x] 多 Agent 模拟面试（规划 / 面试官 / 评估 + 编排）
- [x] SSE 流式输出（带事件 id 断线续传）
- [x] 前端 Trace 可视化（树形 + 瀑布图）
- [x] CI：GitHub Actions 跑 pytest + ruff
- [x] 部署编排：Dockerfile ×2 + Nginx + docker-compose.prod.yml
- [ ] 服务器上首次签发证书并上线，验证 SSE 穿透 Nginx
- [ ] 复盘 Agent（异步任务，生成报告 + 更新用户画像）

**第 4 周起**：真实用户试用 → 从线上 trace 沉淀 30 条评测集（按时间切
tune/holdout）→ judge 校准 + 双人标注 kappa + 配对检验。评测引擎目前
一行代码都还没有，是差异化最重的一块。详见
[`docs/OfferPilot项目方案.md`](docs/OfferPilot项目方案.md) §11。

> ✅ 代码已提交并推送到 GitHub：`woaibiancheng111/OfferPilot`（public）
> 部署用已备案的腾讯云服务器，第 3 周直接上，无等待期。
