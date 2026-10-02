"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ParseJDResponse, SessionResponse, Turn } from "@/lib/types";
import { Badge, Button, ErrorBox, Panel, ScoreBar, TraceLink } from "@/components/ui";

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
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
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
    run("解析 JD", async () => {
      const r = await api.parseJD(jdText);
      setAnalysis(r);
      setStage("ready");
    });

  const onStart = () =>
    run("规划面试", async () => {
      if (!analysis) return;
      const r = await api.startInterview(analysis, userId, resumeText);
      setSession(r);
      setAnswer("");
      setStage("interviewing");
    });

  const onAnswer = () =>
    run("评估并出下一题", async () => {
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">模拟面试</h1>
          <p className="text-xs text-[var(--color-ink-faint)]">
            解析 JD → 规划大纲 → 多轮问答 → 逐轮评估
          </p>
        </div>
        {stage !== "jd" && (
          <Button variant="ghost" onClick={reset}>
            重新开始
          </Button>
        )}
      </div>

      <ErrorBox error={error} />

      {/* ---- 第一步：JD ---- */}
      {(stage === "jd" || stage === "ready") && (
        <Panel
          title="职位描述"
          right={
            <span className="text-xs text-[var(--color-ink-faint)]">
              {analysis ? `第 ${analysis.attempts} 次尝试 · ${analysis.input_tokens + analysis.output_tokens} tokens` : null}
            </span>
          }
        >
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={6}
            className="w-full resize-y rounded-md border border-[var(--color-line)] bg-[var(--color-panel-2)] p-3 text-sm outline-none focus:border-[var(--color-accent)]"
          />
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={onParse} disabled={!!busy || jdText.trim().length < 10}>
              {busy === "解析 JD" ? "解析中…" : analysis ? "重新解析" : "解析 JD"}
            </Button>
            {analysis && (
              <span className="text-xs text-[var(--color-ink-dim)]">
                职级 <Badge tone="accent">{analysis.seniority}</Badge>{" "}
                <Link href={`/traces/${analysis.trace_id}`} className="hover:underline">
                  看这次解析的 trace
                </Link>
              </span>
            )}
          </div>
        </Panel>
      )}

      {/* ---- 解析结果 ---- */}
      {analysis && (
        <Panel title="JD 解析结果">
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <Field label="岗位">{analysis.role_title ?? "—"}</Field>
            <Field label="职级依据">{analysis.seniority_reason}</Field>
            <Field label="业务方向">{analysis.business_domain ?? "—"}</Field>
            <Field label="公司">{analysis.company ?? "—"}</Field>
          </dl>
          <div className="mt-3 space-y-2 text-sm">
            <TagRow label="硬性要求" items={analysis.skills_required} tone="accent" />
            <TagRow label="加分项" items={analysis.skills_nice_to_have} />
            <TagRow label="关键词" items={analysis.keywords} />
          </div>
        </Panel>
      )}

      {/* ---- 第二步：开始面试 ---- */}
      {stage === "ready" && !session && (
        <Panel title="开始面试">
          <label className="block text-xs text-[var(--color-ink-faint)]">
            用户 ID（用于按用户查询历史）
            <input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="mt-1 w-full rounded-md border border-[var(--color-line)] bg-[var(--color-panel-2)] p-2 text-sm outline-none focus:border-[var(--color-accent)]"
            />
          </label>
          <label className="mt-3 block text-xs text-[var(--color-ink-faint)]">
            简历（可选，只进 prompt，不落库）
            <textarea
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              rows={4}
              className="mt-1 w-full resize-y rounded-md border border-[var(--color-line)] bg-[var(--color-panel-2)] p-2 text-sm outline-none focus:border-[var(--color-accent)]"
            />
          </label>
          <div className="mt-3">
            <Button onClick={onStart} disabled={!!busy}>
              {busy === "规划面试" ? "规划中，8-15 秒…" : "开始面试"}
            </Button>
          </div>
        </Panel>
      )}

      {/* ---- 第三步：面试进行中 ---- */}
      {session && (
        <Panel
          title="面试大纲"
          right={<span className="text-xs text-[var(--color-ink-faint)]">共 {session.total_tokens} tokens</span>}
        >
          <ul className="space-y-1.5 text-sm">
            {session.plan.topics.map((t, i) => (
              <li key={i} className="flex gap-2">
                <span className="w-5 shrink-0 text-[var(--color-ink-faint)]">{i + 1}.</span>
                <span>
                  <span className="text-[var(--color-ink)]">{t.topic}</span>{" "}
                  <Badge>{t.difficulty}</Badge>
                  <span className="ml-2 text-xs text-[var(--color-ink-faint)]">{t.why}</span>
                </span>
              </li>
            ))}
          </ul>
          {session.plan.focus_points.length > 0 && (
            <p className="mt-3 text-xs text-[var(--color-ink-dim)]">
              重点验证：{session.plan.focus_points.join("、")}
            </p>
          )}
        </Panel>
      )}

      {session && (
        <div className="space-y-3">
          {session.turns.map((t) => (
            <TurnCard key={t.turn_index} turn={t} />
          ))}
        </div>
      )}

      {session && stage !== "done" && pending && (
        <Panel title={`第 ${pending.turn_index + 1} 轮 · 你的回答`}>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={4}
            placeholder="按你真实的面试状态回答，不用追求好看"
            className="w-full resize-y rounded-md border border-[var(--color-line)] bg-[var(--color-panel-2)] p-3 text-sm outline-none focus:border-[var(--color-accent)]"
          />
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={onAnswer} disabled={!!busy || !answer.trim()}>
              {busy === "评估并出下一题" ? "评估中，约 10 秒…" : "提交回答"}
            </Button>
            <span className="text-xs text-[var(--color-ink-faint)]">
              会先跑评估 Agent，再据此出下一题
            </span>
          </div>
        </Panel>
      )}

      {stage === "done" && session && (
        <Panel title="面试结束">
          <p className="text-sm text-[var(--color-ink-dim)]">
            共 {session.turns.length} 轮，累计 {session.total_tokens} tokens。
          </p>
          <div className="mt-2 text-xs">
            <TraceLink id={session.trace_id} />
          </div>
        </Panel>
      )}

      <div ref={bottomRef} />
    </div>
  );
}

function TurnCard({ turn }: { turn: Turn }) {
  return (
    <Panel
      title={`第 ${turn.turn_index + 1} 轮`}
      right={
        <span className="flex items-center gap-2 text-xs text-[var(--color-ink-faint)]">
          <Badge>{turn.difficulty}</Badge>
          <span>{turn.topic}</span>
        </span>
      }
    >
      <p className="text-sm leading-relaxed">
        <span className="mr-2 text-[var(--color-llm)]">问</span>
        {turn.question}
      </p>
      {turn.answer ? (
        <p className="mt-3 text-sm leading-relaxed">
          <span className="mr-2 text-[var(--color-tool)]">答</span>
          {turn.answer}
        </p>
      ) : (
        <p className="mt-3 text-sm text-[var(--color-ink-faint)]">等待回答…</p>
      )}

      {turn.evaluation && (
        <div className="mt-4 rounded-md bg-[var(--color-panel-2)] p-3">
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone="accent">评估</Badge>
            <ScoreBar label="技术深度" value={turn.evaluation.technical_depth} />
            <ScoreBar label="表达" value={turn.evaluation.clarity} />
            <ScoreBar label="有据" value={turn.evaluation.evidence} />
            <ScoreBar label="切题" value={turn.evaluation.relevance} />
          </div>
          <p className="mt-2 text-xs text-[var(--color-ink-dim)]">
            {turn.evaluation.summary}
          </p>
          <p className="mt-1 text-xs text-[var(--color-ink-faint)]">
            下一步：{actionLabel(turn.evaluation.next_action)} ——{" "}
            {turn.evaluation.follow_up_reason}
          </p>
        </div>
      )}
    </Panel>
  );
}

function actionLabel(a: string): string {
  return { follow_up: "追问", switch_topic: "换题", increase_difficulty: "加难度" }[a] ?? a;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-[var(--color-ink-faint)]">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function TagRow({
  label,
  items,
  tone = "dim",
}: {
  label: string;
  items: string[];
  tone?: "dim" | "accent";
}) {
  if (!items.length) return null;
  return (
    <div className="flex items-start gap-2">
      <span className="w-16 shrink-0 pt-0.5 text-xs text-[var(--color-ink-faint)]">{label}</span>
      <span className="flex flex-wrap gap-1">
        {items.map((s, i) => (
          <Badge key={i} tone={tone}>
            {s}
          </Badge>
        ))}
      </span>
    </div>
  );
}
