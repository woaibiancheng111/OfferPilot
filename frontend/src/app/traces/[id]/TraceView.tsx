"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { SpanNode, TraceDetail } from "@/lib/types";
import { Badge, ErrorBox, JsonBlock, Panel } from "@/components/ui";

const KIND_COLOR: Record<string, string> = {
  agent: "var(--color-agent)",
  llm: "var(--color-llm)",
  tool: "var(--color-tool)",
  custom: "var(--color-custom)",
  retrieval: "var(--color-warn)",
};

const ACTION_LABELS: Record<string, string> = {
  follow_up: "追问",
  switch_topic: "换题",
  increase_difficulty: "加难度",
};

export function TraceView({ id }: { id: string }) {
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getTrace(id)
      .then((d) => alive && setTrace(d))
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!trace) return <p className="text-sm text-[var(--color-ink-faint)]">加载中…</p>;

  const spanCount = trace.spans.reduce((n, s) => n + countSpans(s), 0);

  return (
    <div className="space-y-4">
      <div>
        <Link href="/traces" className="text-xs text-[var(--color-ink-faint)] hover:underline">
          ← 返回列表
        </Link>
        <h1 className="mt-1 text-lg font-semibold">
          {trace.name}{" "}
          <Badge tone={trace.status === "ok" ? "ok" : "bad"}>{trace.status}</Badge>
        </h1>
        <p className="mono mt-1 text-xs text-[var(--color-ink-faint)]">
          {trace.id}
          {trace.user_id && ` · ${trace.user_id}`}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <Stat label="总 tokens" value={String(trace.total_tokens)} />
        <Stat label="总耗时" value={`${trace.latency_ms ?? 0} ms`} />
        <Stat label="span 数" value={String(spanCount)} />
      </div>

      <Panel title="调用树">
        <div className="space-y-1">
          {trace.spans.map((s) => (
            <SpanRow key={s.id} node={s} parentEnd={null} total={trace.latency_ms ?? 0} />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function countSpans(n: SpanNode): number {
  return 1 + (n.children ?? []).reduce((a, c) => a + countSpans(c), 0);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--color-line)] bg-[var(--color-panel)] py-3">
      <div className="mono text-lg">{value}</div>
      <div className="text-xs text-[var(--color-ink-faint)]">{label}</div>
    </div>
  );
}

function SpanRow({
  node,
  parentEnd,
  total,
}: {
  node: SpanNode;
  parentEnd: string | null;
  total: number;
}) {
  const [open, setOpen] = useState(false);
  const children = node.children ?? [];
  const hasDetail =
    node.input !== null || node.output !== null || Object.keys(node.attributes).length > 0;

  const start = new Date(node.started_at).getTime();
  const end = new Date(node.ended_at ?? node.started_at).getTime();
  const parentStart = parentEnd ? new Date(parentEnd).getTime() : start;
  const parentSpan = Math.max(end - parentStart, 1);
  const offsetPct = ((start - parentStart) / parentSpan) * 100;
  const widthPct = Math.max(((end - start) / parentSpan) * 100, 1);
  const globalPct = total > 0 ? ((end - start) / total) * 100 : 0;

  // 评估结果单独提出来放在卡片顶部，比埋在 JSON 里好找得多
  const evalData = readEvaluation(node);

  return (
    <div className="rounded border border-transparent hover:border-[var(--color-line)]">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <span
          className="w-2 shrink-0 rounded-sm"
          style={{ background: KIND_COLOR[node.kind] ?? "var(--color-ink-faint)" }}
        />
        <span className="mono w-16 shrink-0 text-xs" style={{ color: KIND_COLOR[node.kind] }}>
          {node.kind}
        </span>
        <span className="mono w-40 shrink-0 truncate text-sm">{node.name}</span>
        {node.model && (
          <span className="hidden w-32 shrink-0 truncate text-xs text-[var(--color-ink-faint)] sm:inline">
            {node.model}
          </span>
        )}
        {node.prompt_version && (
          <span className="hidden w-20 shrink-0 text-xs text-[var(--color-ink-faint)] md:inline">
            v{node.prompt_version}
          </span>
        )}
        <span className="ml-auto hidden w-24 shrink-0 text-right text-xs text-[var(--color-ink-faint)] sm:inline">
          {node.input_tokens} / {node.output_tokens}
        </span>
        <span className="mono w-20 shrink-0 text-right text-xs text-[var(--color-ink-dim)]">
          {node.latency_ms} ms
        </span>
        {hasDetail && (
          <button
            onClick={() => setOpen(!open)}
            aria-label={open ? "收起详情" : "展开详情"}
            className="w-6 shrink-0 text-xs text-[var(--color-ink-faint)] hover:text-[var(--color-ink)]"
          >
            {open ? "▾" : "▸"}
          </button>
        )}
      </div>

      {/* 相对父 span 的时间条，瀑布图的基本形态 */}
      <div className="mx-2 mb-1 h-1.5 rounded-sm bg-[var(--color-panel-2)]">
        <div
          className="h-full rounded-sm"
          style={{
            marginLeft: `${Math.min(offsetPct, 100)}%`,
            width: `${Math.min(widthPct, 100)}%`,
            background: KIND_COLOR[node.kind] ?? "var(--color-ink-faint)",
            opacity: 0.75,
          }}
          title={`占整条 trace ${globalPct.toFixed(0)}%`}
        />
      </div>

      {open && (
        <div className="mx-2 mb-2 space-y-1.5 rounded bg-[var(--color-panel-2)] p-2">
          {node.error && <p className="text-xs text-[var(--color-bad)]">错误：{node.error}</p>}
          {evalData && <EvaluationCard data={evalData} />}
          <JsonBlock label="attributes" value={node.attributes} />
          <JsonBlock label="input" value={node.input} />
          <JsonBlock label="output" value={node.output} />
        </div>
      )}

      {children.length > 0 && (
        <div className="ml-4 border-l border-[var(--color-line)] pl-2">
          {children.map((c) => (
            <SpanRow key={c.id} node={c} parentEnd={node.ended_at} total={total} />
          ))}
        </div>
      )}
    </div>
  );
}

/** 从用例 span 的 output 里把评估结果挖出来，单独渲染。 */
function readEvaluation(node: SpanNode): Record<string, unknown> | null {
  const out = node.output as { evaluation?: Record<string, unknown> } | null;
  return out && typeof out === "object" && out.evaluation ? out.evaluation : null;
}

function EvaluationCard({ data }: { data: Record<string, unknown> }) {
  const action = String(data.next_action ?? "");
  return (
    <div className="rounded border border-[var(--color-line)] bg-[var(--color-panel)] p-2 text-xs">
      <div className="flex items-center gap-2">
        <Badge tone="accent">本轮评估</Badge>
        <span className="mono text-[var(--color-ink-dim)]">
          深度{String(data.technical_depth)} 表达{String(data.clarity)} 有据
          {String(data.evidence)} 切题{String(data.relevance)}
        </span>
        <Badge>{ACTION_LABELS[action] ?? action}</Badge>
      </div>
      <p className="mt-1 text-[var(--color-ink-dim)]">{String(data.summary ?? "")}</p>
      <p className="mt-0.5 text-[var(--color-ink-faint)]">{String(data.follow_up_reason ?? "")}</p>
    </div>
  );
}
