"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ParseJDResponse, PlanTopic, SessionResponse, Turn } from "@/lib/types";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorBox,
  PageHeader,
  ScoreBar,
  Stat,
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

export default function InterviewPage() {
  const [stage, setStage] = useState<Stage>("jd");
  const [jdText, setJdText] = useState(SAMPLE_JD);
  const [resumeText, setResumeText] = useState(SAMPLE_RESUME);
  const [userId, setUserId] = useState("tester");
  const [analysis, setAnalysis] = useState<ParseJDResponse | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [session?.turns.length]);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
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
      const r = await api.submitAnswer(session.session_id, text);
      setSession(r);
      setAnswer("");
      if (r.finished) setStage("done");
    });

  const reset = () => {
    setStage("jd");
    setAnalysis(null);
    setSession(null);
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

      <div
        className={
          hasSidebar
            ? "grid gap-6 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] lg:items-start"
            // Tailwind 4 的 max-w-* 走的是 spacing scale，max-w-3xl 不再等于 48rem
          : "mx-auto max-w-[48rem]"
        }
      >
        {/* ---------- 主列：对话 ---------- */}
        <div className="order-2 space-y-5 lg:order-1">
          <ErrorBox error={error} />

          {!inInterview && (
            <Card>
              <CardHeader
                title="职位描述"
                hint={analysis ? `${analysis.attempts} 次尝试` : undefined}
              />
              <div className="p-5">
                <textarea
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  rows={7}
                  placeholder="粘贴 JD 原文"
                  className="w-full resize-y rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg-3)] p-3.5 text-sm leading-relaxed outline-none transition-colors placeholder:text-[var(--color-ink-3)] focus:border-[var(--color-accent)] focus:bg-[var(--color-bg-2)]"
                />
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Button onClick={onParse} disabled={!!busy || jdText.trim().length < 10}>
                    {busy === "解析" ? "解析中，约 5 秒…" : analysis ? "重新解析" : "解析 JD"}
                  </Button>
                  {analysis && (
                    <span className="text-xs text-[var(--color-ink-3)]">
                      <TraceLink id={analysis.trace_id} /> · {analysis.input_tokens + analysis.output_tokens} tokens
                    </span>
                  )}
                </div>
              </div>
            </Card>
          )}

          {session ? (
            <>
              {session.turns.map((t) => (
                <TurnCard key={t.turn_index} turn={t} />
              ))}
              <div ref={bottomRef} />
            </>
          ) : (
            !analysis && (
              <EmptyState
                title="还没有开始"
                hint="先解析一份 JD。解析结果会决定面试问什么，所以别急着跳过。"
              />
            )
          )}

          {session && stage !== "done" && pending && (
            <Card>
              <CardHeader title={`第 ${pending.turn_index + 1} 轮 · 你的回答`} />
              <div className="p-5">
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  rows={5}
                  placeholder="按你真实的面试状态回答，不用追求好看"
                  className="w-full resize-y rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg-3)] p-3.5 text-sm leading-relaxed outline-none transition-colors placeholder:text-[var(--color-ink-3)] focus:border-[var(--color-accent)] focus:bg-[var(--color-bg-2)]"
                />
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Button onClick={onAnswer} disabled={!!busy || !answer.trim()}>
                    {busy === "评估" ? "评估中，约 10 秒…" : "提交回答"}
                  </Button>
                  <span className="text-xs text-[var(--color-ink-3)]">
                    会先跑评估 Agent，再据此决定下一题
                  </span>
                </div>
              </div>
            </Card>
          )}

          {stage === "done" && session && (
            <Card>
              <div className="p-5">
                <p className="text-sm font-medium">面试结束</p>
                <p className="muted mt-1 text-sm">
                  共 {session.turns.length} 轮，累计 {session.total_tokens} tokens。
                </p>
                <p className="mt-3">
                  <Link
                    href={`/traces/${session.trace_id}`}
                    className="text-xs text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-accent)]"
                  >
                    看最后这一轮的调用树 →
                  </Link>
                </p>
              </div>
            </Card>
          )}
        </div>

        {/* ---------- 侧栏：静态资料 ---------- */}
        {hasSidebar && (
        <aside className="order-1 space-y-5 lg:order-2 lg:sticky lg:top-20">
          {analysis && (
            <Card>
              <CardHeader title="JD 解析" />
              <div className="space-y-4 p-5">
                <dl className="space-y-3 text-sm">
                  <Field label="岗位">{analysis.role_title ?? "—"}</Field>
                  <Field label="职级依据">{analysis.seniority_reason}</Field>
                  <Field label="业务方向">{analysis.business_domain ?? "—"}</Field>
                </dl>
                <div className="space-y-2.5 border-t border-[var(--color-line)] pt-4">
                  <TagRow label="硬性要求" items={analysis.skills_required} tone="accent" />
                  <TagRow label="加分项" items={analysis.skills_nice_to_have} />
                  <TagRow label="关键词" items={analysis.keywords} />
                </div>
              </div>
            </Card>
          )}

          {stage === "ready" && !session && (
            <Card>
              <CardHeader title="开始面试" />
              <div className="space-y-4 p-5">
                <label className="block">
                  <span className="label">用户 ID</span>
                  <input
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    className="mono mt-1.5 w-full rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg-3)] px-3 py-2 text-sm outline-none transition-colors focus:border-[var(--color-accent)] focus:bg-[var(--color-bg-2)]"
                  />
                </label>
                <label className="block">
                  <span className="label">简历（可选）</span>
                  <span className="mt-1.5 block text-[11px] leading-relaxed text-[var(--color-ink-3)]">
                    只进 prompt，不落库
                  </span>
                  <textarea
                    value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    rows={4}
                    className="mt-1.5 w-full resize-y rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg-3)] p-3 text-sm leading-relaxed outline-none transition-colors focus:border-[var(--color-accent)] focus:bg-[var(--color-bg-2)]"
                  />
                </label>
                <Button onClick={onStart} disabled={!!busy} className="w-full">
                  {busy === "规划" ? "规划中，8-15 秒…" : "开始面试"}
                </Button>
              </div>
            </Card>
          )}

          {session && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Stat label="轮次" value={`${session.turns.length}`} />
                <Stat label="tokens" value={`${session.total_tokens}`} />
              </div>

              <Card>
                <CardHeader title="面试大纲" hint={`${session.plan.topics.length} 个考察点`} />
                <ol className="space-y-3 p-5">
                  {session.plan.topics.map((t, i) => (
                    <TopicRow key={i} index={i} topic={t} active={pending?.topic === t.topic} />
                  ))}
                </ol>
                {session.plan.focus_points.length > 0 && (
                  <div className="border-t border-[var(--color-line)] px-5 py-4">
                    <span className="label">重点验证</span>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
                      {session.plan.focus_points.join("、")}
                    </p>
                  </div>
                )}
              </Card>
            </>
          )}
        </aside>
        )}
      </div>
    </>
  );
}

function TurnCard({ turn }: { turn: Turn }) {
  const ev = turn.evaluation;
  return (
    <Card as="article">
      <CardHeader
        title={`第 ${turn.turn_index + 1} 轮`}
        right={
          <span className="flex items-center gap-2">
            <Badge>{turn.difficulty}</Badge>
            <span className="text-[11px] text-[var(--color-ink-3)]">{turn.topic}</span>
          </span>
        }
      />
      <div className="space-y-4 p-5">
        <p className="text-[15px] leading-[1.7] text-pretty">
          <span className="mono mr-2 text-[11px] font-semibold text-[var(--color-k-llm)]">问</span>
          {turn.question}
        </p>
        {turn.answer ? (
          <p className="text-[15px] leading-[1.7] text-pretty">
            <span className="mono mr-2 text-[11px] font-semibold text-[var(--color-k-tool)]">答</span>
            {turn.answer}
          </p>
        ) : (
          <p className="text-sm text-[var(--color-ink-3)]">等待回答…</p>
        )}

        {ev && (
          <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-bg-3)]/60 p-4">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              <Badge tone="accent">评估</Badge>
              <ScoreBar label="技术深度" value={ev.technical_depth} />
              <ScoreBar label="表达" value={ev.clarity} />
              <ScoreBar label="有据" value={ev.evidence} />
              <ScoreBar label="切题" value={ev.relevance} />
            </div>
            <p className="muted mt-3 text-[13px]">{ev.summary}</p>
            <p className="mt-2 border-l-2 border-[var(--color-k-custom)]/40 pl-3 text-[13px] leading-relaxed text-[var(--color-ink-2)]">
              下一步{ACTION_LABELS[ev.next_action] ?? ev.next_action} —— {ev.follow_up_reason}
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

const ACTION_LABELS: Record<string, string> = {
  follow_up: "追问",
  switch_topic: "换题",
  increase_difficulty: "加难度",
};

function TopicRow({ index, topic, active }: { index: number; topic: PlanTopic; active: boolean }) {
  return (
    <li className="flex gap-3">
      <span className="mono mt-[1px] w-4 shrink-0 text-[11px] text-[var(--color-ink-3)]">
        {index + 1}
      </span>
      <div className={active ? "text-[var(--color-ink)]" : ""}>
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium">{topic.topic}</span>
          {active && <Badge tone="accent">进行中</Badge>}
          <span className="text-[11px] text-[var(--color-ink-3)]">{topic.difficulty}</span>
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-[var(--color-ink-3)]">{topic.why}</p>
      </div>
    </li>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="mt-1 text-[13px] leading-relaxed text-[var(--color-ink-2)]">{children}</dd>
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
