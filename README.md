# OfferPilot

求职 Agent + 自研观测评测平台。完整方案见 [`docs/OfferPilot项目方案.md`](docs/OfferPilot项目方案.md)（v2，含修订记录）。

当前进度：**第 1 周**。已完成手写 agent loop、双厂商模型抽象层、Trace SDK、落库前脱敏、prompt 内容 hash 版本号、Trace 查询 API 和数据库迁移，85 个测试全绿。

## 快速开始

需要 Python 3.12、[uv](https://docs.astral.sh/uv/) 和 Docker。

```bash
# 1. 启动 PostgreSQL（端口 55432）和 Redis（端口 56379）
docker compose up -d

# 2. 安装依赖并建表
cd backend
uv sync
cp .env.example .env        # 填入 ANTHROPIC_API_KEY
uv run alembic upgrade head

# 3. 跑测试（不需要 API key，也不需要数据库）
uv run pytest

# 4. 启动服务
uv run uvicorn app.main:app --reload --port 18088
```

打开 http://localhost:18088/docs 可以看到自动生成的接口文档。

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

接第三方中转站时再补一个 `OPENAI_BASE_URL` 即可。模型的价格表在 `app/llm/pricing.py`，
换新模型记得同步加价目表——不在表里的模型成本会记为 0 并打一条告警日志。

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
backend/
├── app/
│   ├── agents/
│   │   ├── loop.py          # 手写的 agent loop
│   │   ├── prompts/         # prompt 模板与内容 hash 版本号
│   │   └── demo.py          # 演示 Agent（计算器 + 时间查询）
│   ├── llm/
│   │   ├── base.py          # 与厂商无关的消息格式和 LLMClient 协议
│   │   ├── errors.py        # 与厂商无关的异常
│   │   ├── factory.py       # 按 .env 构造客户端
│   │   ├── anthropic_provider.py  # Claude 适配器
│   │   ├── openai_provider.py     # OpenAI 兼容端点适配器
│   │   └── pricing.py       # 按厂商分表的成本估算
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

**模型适配**（`app/llm/`）
- 换厂商、换模型只改 `.env` 里的 `LLM_VENDOR` / `LLM_MODEL`，代码不动
- 业务层只认识 `app/llm/base.py` 里的消息格式和 `LLMClient` 协议，不 import 任何厂商 SDK
- 厂商异常在 provider 层翻译成中立异常（`errors.py`），API 层据此映射 HTTP 状态码，不认 `anthropic.AuthenticationError` 这类具体类型
- 两家的协议差异（system 的位置、工具结果的消息形态、工具参数的 JSON 字符串）都在各自 provider 里转换
- 两家对 token 的口径不同，所以成本估算按厂商分表：Anthropic 的 `input_tokens` 不含缓存，OpenAI 的 `prompt_tokens` 已含缓存，混算会算错
- `prompt_cache_key` 由 system 提示自动派生，保证同一套提示稳定命中缓存

**Prompt 版本号**（`app/agents/prompts/`）
- 版本号是 `sha256(prompt)[:8]`，`run_agent` 在没传 `prompt_version` 时自动算
- 没有手写版本号这个选项，也就没有"改了 prompt 忘了改版本号"导致前后对比悄悄失效的问题
- agent span 和它下面的 llm span 都带版本号，回归时能按版本分组

## 下一步（第 2 周）

- [ ] JD 解析 Agent（结构化输出）
- [ ] 模拟面试核心流程（文字版）
- [ ] SSE 流式输出（带事件 id 断线续传）
- [ ] 前端 Trace 可视化（树形 + 瀑布图）
- [ ] CI：GitHub Actions 跑 pytest + ruff

> ⚠️ 本仓库目前仍是**零 commit** 状态，动手改代码前先提一次。
> 另外 ICP 备案有 1–3 周等待期，第 1 周就该启动。
