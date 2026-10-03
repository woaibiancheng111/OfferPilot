"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { streamSse } from "@/lib/stream";
import type {
  NextTurn,
  ParseJDResponse,
  PlanTopic,
  QuestionEvent,
  SessionEvent,
  SessionResponse,
  Turn,
  TurnDoneEvent,
  TurnEvaluation,
  TurnStartEvent,
} from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorBox,
  PageHeader,
  ScoreMeter,
  TraceLink,
} from "@/components/ui";

const SAMPLE_JD = `后端工程师（社招）

负责企业服务 SaaS 平台的后端研发，要求 3 年以上 Python 和 PostgreSQL 经验，
熟悉 Redis 优先。Kubernetes 有经验加分。

职责：
- 设计并实现高并发服务接口
- 参与数据库 schema 设计与性能优化`;

const SAMPLE_RESUME = `2021-2024 XX公司 后端工程师
- 负责 Python 微服务，用 FastAPI + asyncpg，Redis 做缓存
- 用 Kubernetes 做容器编排
- PostgreSQL 表结构设计，做过索引优化`;

type Stage = "jd" | "ready" | "interviewing" | "done";

/** 正在流式接收中的那一轮。单独放 state，免得一收到 token 就重算整个会话。 */
type Live = {
  turnIndex: number;
  topic: string;
  evaluation: TurnEvaluation | null;
  question: string;
} | null;

/**
 * 把流式结果合并进会话。
 *
 * 服务端的 session 事件只带新出现的那一轮，已回答那轮的评估在 turn_start 里，
 * 所以这里在前端合一次——避免为了一个增量把整个会话再拉一遍。
 */
function applyStream(
  session: SessionResponse,
  answer: string,
  started: TurnStartEvent,
  last: SessionEvent,
): SessionResponse {
  const turns: Turn[] = session.turns.map((t) =>
    t.turn_index === started.turn_index
      ? { ...t, answer, evaluation: started.evaluation }
      : t,
  );
  const next = last.next_turn as NextTurn | null;
  if (next) {
    turns.push({
      turn_index: next.turn_index,
      topic: next.topic,
      difficulty: next.difficulty,
      question: next.question,
      answer: null,
      evaluation: null,
    });
  }
  return { ...session, turns, finished: last.finished, total_tokens: last.total_tokens };
}

export default function InterviewPage() {
  const [stage, setStage] = useState<Stage>("jd");
  const [jdText, setJdText] = useState(SAMPLE_JD);
  const [resumeText, setResumeText] = useState(SAMPLE_RESUME);
  const [userId, setUserId] = useState("tester");
  const [analysis, setAnalysis] = useState<ParseJDResponse | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [live, setLive] = useState<Live>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // 卸载或「重新开始」时中断还在进行的流，否则它会在后台继续烧 token
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [session?.turns.length, live?.question]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError(e instanceof ApiError ? e.message : String(e));
      setLive(null);
    } finally {
      setBusy(null);
    }
  }

  const onParse = () =>
    run("解析", async () => {
      const r = await api.parseJD(jdText);
      setAnalysis(r);
      setSession(null);
      setStage("ready");
    });

  const onStart = () =>
    run("规划", async () => {
      if (!analysis) return;
      const r = await api.startInterview(analysis, userId, resumeText);
      setSession(r);
      setAnswer("");
      setStage("interviewing");
    });

  const onAnswer = () =>
    run("评估", async () => {
      if (!session) return;
      const text = answer.trim();
      if (!text) return;

      const controller = new AbortController();
      abortRef.current = controller;
      setAnswer("");
      setLive({ turnIndex: 0, topic: "", evaluation: null, question: "" });

      let started: TurnStartEvent | null = null;
      let done: TurnDoneEvent | null = null;
      let last: SessionEvent | null = null;
      let lastEventId = 0;
      const opts = {
        signal: controller.signal,
        get lastEventId() {
          return lastEventId;
        },
      };

      const stream = streamSse(
        `/api/interview/${session.session_id}/answer/stream`,
        { answer: text },
        opts,
      );

      for await (const ev of stream) {
        lastEventId = ev.id;
        switch (ev.event) {
          case "turn_start": {
            const d = ev.data as unknown as TurnStartEvent;
            started = d;
            setLive({ turnIndex: d.turn_index, topic: d.topic, evaluation: d.evaluation, question: "" });
            setBusy("提问");
            break;
          }
          case "question": {
            const d = ev.data as unknown as QuestionEvent;
            setLive((prev) => (prev ? { ...prev, question: prev.question + d.delta } : prev));
            break;
          }
          case "turn_done": {
            done = ev.data as unknown as TurnDoneEvent;
            setLive((prev) => (prev ? { ...prev, question: done!.question } : prev));
            break;
          }
          case "session":
            last = ev.data as unknown as SessionEvent;
            break;
          case "error":
            throw new Error((ev.data as { message: string }).message);
        }
      }

      if (!started || !done || !last) throw new Error("流提前结束，没拿到完整结果");
      setSession(applyStream(session, text, started, last));
      setLive(null);
      if (last.finished) setStage("done");
    });

  const reset = () => {
    abortRef.current?.abort();
    setStage("jd");
    setAnalysis(null);
    setSession(null);
    setLive(null);
    setAnswer("");
    setError(null);
  };

  const pending = session?.turns.find((t) => !t.answer) ?? null;
  const inInterview = stage === "interviewing" || stage === "done";
  // 侧栏没内容时不分栏，否则右侧会空掉一大块，比留白更难看
  const hasSidebar = Boolean(analysis) || (stage === "ready" && !session) || Boolean(session);

  return (
    <>
      <PageHeader
        title="模拟面试"
        description="粘贴职位描述，解析出考察点，逐轮问答并给出可解释的评估。"
        action={
          stage !== "jd" && (
            <Button variant="ghost" onClick={reset}>
              重新开始
            </Button>
          )
        }
      />

      {/*
        始终双栏。窄列居中会在两侧留出大片空白，页面看起来像没做完；
        右栏在解析前先承担流程说明，开始后再换成大纲和设置。
      */}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,0.95fr)] lg:items-start lg:gap-12">
        {/* ---------- 主列：面试记录 ---------- */}
        <div className="order-2 space-y-6 lg:order-1">
          <ErrorBox error={error} />

          {!inInterview && (
            <Card>
              <CardHeader
                title="职位描述"
                hint={analysis ? `已解析 ${analysis.attempts} 次` : undefined}
              />
              <div className="p-6">
                <Field className="min-h-[16rem]">
                  <textarea
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                    rows={11}
                    placeholder="粘贴 JD 原文"
                    className={TEXTAREA}
                  />
                </Field>
                <div className="mt-5 flex flex-wrap items-center gap-4">
                  <Button onClick={onParse} disabled={!!busy || jdText.trim().length < 10}>
                    {busy === "解析" ? "解析中，约 5 秒" : analysis ? "重新解析" : "解析 JD"}
                  </Button>
                  {analysis && (
                    <span className="flex items-center gap-2 text-[12.5px] text-ink-3">
                      <TraceLink id={analysis.trace_id} />
                      <span className="mono">
                        {(analysis.input_tokens + analysis.output_tokens).toLocaleString()} tokens
                      </span>
                    </span>
                  )}
                </div>
              </div>
            </Card>
          )}

          {session && (
            <>
              {/*
                一条连续的时间轴，而不是一轮一张卡片。轮次本身就是序列，
                所以左边的轴和节点在编码真实信息，不是装饰。
              */}
              <ol className="animate-rise">
                {session.turns.map((t, i) => (
                  <TurnEntry key={t.turn_index} turn={t} isLast={i === session.turns.length - 1 && !live} />
                ))}
                {live && <LiveEntry live={live} busy={busy} isLast />}
              </ol>
              <div ref={bottomRef} />
            </>
          )}

          {session && stage !== "done" && pending && (
            <Card>
              <CardHeader title={`第 ${pending.turn_index + 1} 轮，你的回答`} />
              <div className="p-6">
                <Field className="min-h-[8rem]">
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    rows={5}
                    placeholder="按你真实的面试状态回答，不用追求好看"
                    className={TEXTAREA}
                  />
                </Field>
                <div className="mt-5 flex flex-wrap items-center gap-4">
                  <Button onClick={onAnswer} disabled={!!busy || !answer.trim()}>
                    {busy === "评估" ? "评估中，约 10 秒" : "提交回答"}
                  </Button>
                  <span className="text-[12.5px] text-ink-3">先跑评估 Agent，再据此决定下一题</span>
                </div>
              </div>
            </Card>
          )}

          {stage === "done" && session && (
            <Card>
              <div className="p-6">
                <p className="text-[16px] font-semibold text-ink">面试结束</p>
                <p className="mt-2 text-[14px] leading-[1.65] text-ink-2">
                  共 {session.turns.length} 轮，累计 {session.total_tokens.toLocaleString()} tokens。
                </p>
                <Link
                  href={`/traces/${session.trace_id}`}
                  className="mt-5 inline-flex items-center gap-2 text-[13.5px] text-ink-2 transition-colors hover:text-accent"
                >
                  <span className="mono rounded-xs bg-surface-2 px-1.5 py-0.5 text-[11.5px] text-ink-3">
                    {session.trace_id.slice(0, 8)}
                  </span>
                  看最后一轮的调用树
                </Link>
              </div>
            </Card>
          )}
        </div>

        {/* ---------- 侧栏：一个面板，内部用发丝线分段 ---------- */}
        <aside className="order-1 lg:order-2 lg:sticky lg:top-24">
          {!hasSidebar ? (
            <FlowPanel />
          ) : (
            <Card as="div" className="overflow-hidden">
              {analysis && (
                <SideSection title="JD 解析">
                  <dl className="space-y-4">
                    <Field label="岗位">{analysis.role_title ?? "—"}</Field>
                    <Field label="职级依据">{analysis.seniority_reason}</Field>
                    <Field label="业务方向">{analysis.business_domain ?? "—"}</Field>
                  </dl>
                  <div className="mt-5 space-y-3">
                    <TagRow label="硬性要求" items={analysis.skills_required} tone="accent" />
                    <TagRow label="加分项" items={analysis.skills_nice_to_have} />
                    <TagRow label="关键词" items={analysis.keywords} />
                  </div>
                </SideSection>
              )}

              {stage === "ready" && !session && (
                <SideSection title="开始面试">
                  <div className="space-y-5">
                    <label className="block">
                      <span className="label">用户 ID</span>
                      <input
                        value={userId}
                        onChange={(e) => setUserId(e.target.value)}
                        className={INPUT}
                      />
                    </label>
                    <label className="block">
                      <span className="label">简历，可选</span>
                      <textarea
                        value={resumeText}
                        onChange={(e) => setResumeText(e.target.value)}
                        rows={4}
                        className={`${INPUT} mt-2 resize-y leading-[1.7]`}
                      />
                      <span className="mt-2 block text-[12px] leading-[1.6] text-ink-3">
                        只进 prompt，不落库
                      </span>
                    </label>
                    <Button onClick={onStart} disabled={!!busy} className="w-full">
                      {busy === "规划" ? "规划中，8 到 15 秒" : "开始面试"}
                    </Button>
                  </div>
                </SideSection>
              )}

              {session && (
                <>
                  <div className="grid grid-cols-2 divide-x divide-line border-b border-line">
                    <Cell label="轮次" value={String(session.turns.length)} />
                    <Cell label="tokens" value={session.total_tokens.toLocaleString()} />
                  </div>

                  <SideSection title="面试大纲" hint={`${session.plan.topics.length} 个考察点`}>
                    <ol className="space-y-4">
                      {session.plan.topics.map((t, i) => (
                        <TopicRow key={i} index={i} topic={t} active={pending?.topic === t.topic} />
                      ))}
                    </ol>
                    {session.plan.focus_points.length > 0 && (
                      <div className="mt-5 border-t border-line pt-4">
                        <span className="label">重点验证</span>
                        <p className="mt-2 text-[13.5px] leading-[1.65] text-ink-2">
                          {session.plan.focus_points.join("、")}
                        </p>
                      </div>
                    )}
                  </SideSection>
                </>
              )}
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}

const TEXTAREA =
  "w-full resize-y rounded-md border border-line bg-surface-2 px-4 py-3.5 text-[15px] leading-[1.7] " +
  "text-ink outline-none transition-colors duration-150 placeholder:text-ink-3 " +
  "hover:border-line-2 focus:border-accent/60 focus:bg-surface-3";

const INPUT =
  "mono mt-2 w-full rounded-md border border-line bg-surface-2 px-3.5 py-2.5 text-[14px] text-ink " +
  "outline-none transition-colors duration-150 placeholder:text-ink-3 focus:border-accent/60 focus:bg-surface-3";

/* ---------- 侧栏 ---------- */

const STEPS = [
  {
    title: "解析 JD",
    body: "抽出岗位、职级依据、硬性要求和关键词。这份结果决定后面问什么。",
  },
  {
    title: "确认面试大纲",
    body: "按考察点排出轮次，标明每个点为什么被选中，开始前可以先过一眼。",
  },
  {
    title: "逐轮问答",
    body: "回答后先出评估，再据此决定下一题，问题会跟着你的回答走。",
  },
];

const OUTPUTS = [
  "四个维度的打分和一段总结",
  "下一步打算追问还是换题，以及理由",
  "每一步的调用树、耗时和 token",
];

/**
 * 解析之前的右栏。
 *
 * 这里原本是空的，下面还挂一个大号空状态框，整页看着像没做完。
 * 换成讲清楚流程和产出：第一次来的人需要知道解析完会发生什么，
 * 右栏也就不是硬凑出来的第二列。
 */
function FlowPanel() {
  return (
    <Card as="div" className="overflow-hidden">
      <SideSection title="流程">
        {/* 编号在这里是真的：这三步有先后，不是随便排的装饰项 */}
        <ol className="space-y-5">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-3.5">
              <span className="num w-4 shrink-0 pt-[3px] text-[12.5px] text-ink-3">{i + 1}</span>
              <div>
                <p className="text-[13.5px] font-medium text-ink">{s.title}</p>
                <p className="mt-1.5 text-[12.5px] leading-[1.65] text-ink-3">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </SideSection>

      <SideSection title="每轮会给什么">
        <ul className="space-y-3">
          {OUTPUTS.map((o) => (
            <li key={o} className="flex gap-2.5 text-[13.5px] leading-[1.6] text-ink-2">
              <span className="mt-[7px] size-[5px] shrink-0 rotate-45 bg-accent-solid" aria-hidden />
              {o}
            </li>
          ))}
        </ul>
      </SideSection>
    </Card>
  );
}

function SideSection({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-line px-6 py-5 last:border-b-0">
      <div className="mb-4 flex items-baseline gap-2.5">
        <h2 className="text-[14px] font-semibold text-ink">{title}</h2>
        {hint && <span className="text-[12.5px] text-ink-3">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-6 py-4">
      <div className="num text-[22px] font-semibold leading-none text-ink">{value}</div>
      <div className="mt-2 text-[12.5px] text-ink-3">{label}</div>
    </div>
  );
}

function TopicRow({ index, topic, active }: { index: number; topic: PlanTopic; active: boolean }) {
  return (
    <li className="flex gap-3">
      <span
        className={
          "num mt-[1px] w-4 shrink-0 text-[12.5px] " +
          (active ? "text-accent" : "text-ink-3")
        }
      >
        {index + 1}
      </span>
      <div className={active ? "text-ink" : ""}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13.5px] font-medium">{topic.topic}</span>
          {active && <Badge tone="accent">进行中</Badge>}
          <span className="text-[12px] text-ink-3">{topic.difficulty}</span>
        </div>
        <p className="mt-1.5 text-[12.5px] leading-[1.6] text-ink-3">{topic.why}</p>
      </div>
    </li>
  );
}

/* ---------- 时间轴 ---------- */

function TurnEntry({ turn, isLast }: { turn: Turn; isLast: boolean }) {
  return (
    <li className="relative pb-11 last:pb-0">
      {!isLast && <span aria-hidden className="absolute bottom-0 left-[15px] top-[12px] w-px bg-line" />}
      <Node tone={turn.answer ? "done" : "pending"} />

      <div className="flex h-6 items-center gap-3 pl-12">
        <span className="num absolute left-0 top-[3px] text-[12.5px] text-ink-3">
          {String(turn.turn_index + 1).padStart(2, "0")}
        </span>
        <span className="text-[13.5px] text-ink-2">{turn.topic}</span>
        <Badge>{turn.difficulty}</Badge>
      </div>

      <div className="mt-5 space-y-5 pl-12">
        <Speech who="面试官" tone="ask">
          {turn.question}
        </Speech>

        {turn.answer ? (
          <Speech who="你" tone="answer">
            {turn.answer}
          </Speech>
        ) : (
          <p className="text-[14px] text-ink-3">等你的回答</p>
        )}

        {turn.evaluation && <EvaluationPanel evaluation={turn.evaluation} />}
      </div>
    </li>
  );
}

/**
 * 流式接收中的那一轮。
 *
 * 评估先到、问题后到，所以这两个阶段是分开展示的：
 * 等评估的那几秒先显示上一轮的打分，别让用户对着空白等待。
 */
function LiveEntry({
  live,
  busy,
  isLast,
}: {
  live: NonNullable<Live>;
  busy: string | null;
  isLast: boolean;
}) {
  const streaming = live.question.length > 0;
  return (
    <li className="relative pb-11 last:pb-0">
      {!isLast && <span aria-hidden className="absolute bottom-0 left-[15px] top-[12px] w-px bg-line" />}
      <Node tone="live" />

      <div className="flex h-6 items-center gap-3 pl-12">
        <span className="num absolute left-0 top-[3px] text-[12.5px] text-accent">
          {String(live.turnIndex + 1).padStart(2, "0")}
        </span>
        {live.topic && <span className="text-[13.5px] text-ink-2">{live.topic}</span>}
        <span className="relative ml-auto flex items-center gap-2 overflow-hidden text-[12px] text-accent">
          <span className="size-[6px] shrink-0 animate-pulse rounded-full bg-accent" />
          正在生成
        </span>
      </div>

      <div className="mt-5 space-y-5 pl-12">
        {live.evaluation && <EvaluationPanel evaluation={live.evaluation} delay={0} />}

        {streaming ? (
          <Speech who="面试官" tone="ask">
            {live.question}
            <span className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[2px] animate-pulse bg-accent" />
          </Speech>
        ) : (
          <p className="text-[14px] text-ink-3">
            {busy === "评估" ? "正在评估你上一轮的回答" : "准备中"}
          </p>
        )}
      </div>
    </li>
  );
}

function Node({ tone }: { tone: "done" | "pending" | "live" }) {
  const bg =
    tone === "live" ? "var(--color-accent)" : tone === "done" ? "var(--color-line-2)" : "var(--color-bg)";
  return (
    <span
      aria-hidden
      className="absolute left-[9px] top-[5px] size-[13px] rounded-full border-[4px] border-bg"
      style={{ background: bg }}
    />
  );
}

/**
 * 一段发言。
 *
 * 说话人是一个普通词，不是一个等宽的「问」字色块——11px 的方块字在
 * 正文旁边读起来像补丁。而且靠缩进和左边线区分正反对，比给每段套框更安静。
 */
function Speech({
  who,
  tone,
  children,
}: {
  who: string;
  tone: "ask" | "answer";
  children: React.ReactNode;
}) {
  return (
    <div className={tone === "answer" ? "border-l-2 border-k-tool/45 pl-5" : ""}>
      <span
        className={
          "mr-2.5 text-[12.5px] font-medium " + (tone === "answer" ? "text-k-tool" : "text-ink-3")
        }
      >
        {who}
      </span>
      <p className="prose inline text-ink">{children}</p>
    </div>
  );
}

/* ---------- 评估 ---------- */

const ACTION_LABELS: Record<string, string> = {
  follow_up: "追问",
  switch_topic: "换题",
  increase_difficulty: "加难度",
};

const DIMS: [keyof TurnEvaluation, string][] = [
  ["technical_depth", "深度"],
  ["clarity", "表达"],
  ["evidence", "有据"],
  ["relevance", "切题"],
];

/**
 * 评估面板。历史轮和流式中的当前轮共用，保证两处显示一致。
 *
 * 左边那个大号均分是整个界面对「机器的判断」唯一的强调——金色留给它，
 * 剩下的四维用安静的量表带过。均分就是四维的算术平均，不做任何加权。
 */
function EvaluationPanel({ evaluation, delay = 90 }: { evaluation: TurnEvaluation; delay?: number }) {
  const scores = DIMS.map(([k]) => Number(evaluation[k]));
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const meanColor = mean >= 4 ? "var(--color-ok)" : mean >= 3 ? "var(--color-warn)" : "var(--color-bad)";

  return (
    <div className="panel-flat animate-rise p-5">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:gap-7">
        <div className="shrink-0 sm:w-24 sm:border-r sm:border-line sm:pr-6">
          <div className="num text-[38px] font-semibold leading-none" style={{ color: meanColor }}>
            {mean.toFixed(1)}
          </div>
          <div className="mt-2 text-[12.5px] text-ink-3">四维均分</div>
        </div>

        <div className="grid flex-1 gap-2.5 sm:grid-cols-2 sm:gap-x-7">
          {DIMS.map(([key, label], i) => (
            <ScoreMeter
              key={key}
              label={label}
              value={Number(evaluation[key])}
              delay={delay + i * 60}
            />
          ))}
        </div>
      </div>

      <p className="mt-5 text-[14px] leading-[1.7] text-ink-2">{evaluation.summary}</p>

      <div className="mt-4 flex gap-3 border-t border-line pt-4">
        <Badge tone="custom" className="h-fit shrink-0">
          下一步{ACTION_LABELS[evaluation.next_action] ?? evaluation.next_action}
        </Badge>
        <p className="text-[13.5px] leading-[1.65] text-ink-3">{evaluation.follow_up_reason}</p>
      </div>
    </div>
  );
}

/* ---------- 小件 ---------- */

function Field({
  label,
  children,
  className = "",
}: {
  label?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      {label && <div className="label mb-1.5">{label}</div>}
      {children}
    </div>
  );
}

function TagRow({
  label,
  items,
  tone = "neutral",
}: {
  label: string;
  items: string[];
  tone?: "neutral" | "accent";
}) {
  if (!items.length) return null;
  return (
    <div className="flex items-start gap-3">
      <span className="label w-14 shrink-0 pt-[5px]">{label}</span>
      <span className="flex flex-wrap gap-1.5">
        {items.map((s, i) => (
          <Badge key={i} tone={tone}>
            {s}
          </Badge>
        ))}
      </span>
    </div>
  );
}
