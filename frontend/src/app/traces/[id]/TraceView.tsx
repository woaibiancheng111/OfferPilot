"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { SpanNode, TraceDetail } from "@/lib/types";
import { Badge, Card, CardHeader, ErrorBox, JsonBlock, PageHeader, Skeleton, Stat } from "@/components/ui";

/** span 类型 = 仪表盘配色，同一色温家族的低饱和度，靠色相区分层级 */
const KIND: Record<string, { color: string; label: string }> = {
  custom: { color: "var(--color-k-custom)", label: "用例" },
  agent: { color: "var(--color-k-agent)", label: "agent" },
  llm: { color: "var(--color-k-llm)", label: "模型" },
  tool: { color: "var(--color-k-tool)", label: "工具" },
  retrieval: { color: "var(--color-warn)", label: "检索" },
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

  if (!trace) {
    return (
      <>
        <PageHeader title="加载中" />
        <Card>
          <div className="space-y-3 p-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-3 w-2" />
                <Skeleton className="h-3.5 w-28" />
                <Skeleton className="ml-auto h-2.5 w-24" />
              </div>
            ))}
          </div>
        </Card>
      </>
    );
  }

  const spanCount = trace.spans.reduce((n, s) => n + countSpans(s), 0);
  const total = trace.latency_ms ?? 0;

  return (
    <>
      <div className="mb-6">
        <Link
          href="/traces"
          className="text-[11px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink-2)]"
        >
          ← 所有 trace
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="mono text-[22px] font-semibold tracking-tight">{trace.name}</h1>
          <Badge tone={trace.status === "ok" ? "ok" : "bad"}>{trace.status}</Badge>
          {trace.user_id && <span className="text-[12px] text-[var(--color-ink-3)]">{trace.user_id}</span>}
        </div>
        <p className="mono mt-1.5 text-[11px] text-[var(--color-ink-3)]">{trace.id}</p>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-3">
        <Stat label="总 tokens" value={trace.total_tokens.toLocaleString()} />
        <Stat label="总耗时" value={`${(total / 1000).toFixed(2)}s`} />
        <Stat label="span 数" value={String(spanCount)} />
      </div>

      <Card>
        <CardHeader
          title="调用树"
          right={
            <div className="flex flex-wrap items-center gap-3">
              {Object.entries(KIND).map(([k, v]) => (
                <span key={k} className="flex items-center gap-1.5 text-[11px] text-[var(--color-ink-3)]">
                  <span className="size-2 rounded-[2px]" style={{ background: v.color }} />
                  {v.label}
                </span>
              ))}
            </div>
          }
        />
        <div className="space-y-0.5 p-4">
          {trace.spans.map((s) => (
            <SpanRow key={s.id} node={s} parentStart={null} parentEnd={null} total={total} />
          ))}
        </div>
      </Card>
    </>
  );
}

function countSpans(n: SpanNode): number {
  return 1 + (n.children ?? []).reduce((a, c) => a + countSpans(c), 0);
}

function SpanRow({
  node,
  parentStart,
  parentEnd,
  total,
}: {
  node: SpanNode;
  parentStart: number | null;
  parentEnd: number | null;
  total: number;
}) {
  const [open, setOpen] = useState(false);
  const children = node.children ?? [];
  const kind = KIND[node.kind] ?? { color: "var(--color-ink-3)", label: node.kind };
  const hasDetail =
    node.input !== null || node.output !== null || Object.keys(node.attributes).length > 0;

  const start = new Date(node.started_at).getTime();
  const end = new Date(node.ended_at ?? node.started_at).getTime();
  const base = parentStart ?? start;
  const span = Math.max((parentEnd ?? end) - base, 1);
  const offsetPct = Math.min(((start - base) / span) * 100, 100);
  const widthPct = Math.max(((end - start) / span) * 100, 0.75);

  return (
    <div className="rounded-[var(--radius-sm)] transition-colors duration-150 hover:bg-[var(--color-bg-3)]/40">
      <div className="flex items-center gap-3 px-2 py-1.5">
        <span className="size-2 shrink-0 rounded-[2px]" style={{ background: kind.color }} />

        <span className="mono w-14 shrink-0 text-[11px]" style={{ color: kind.color }}>
          {node.kind}
        </span>
        <span className="mono w-44 shrink-0 truncate text-[13px] text-[var(--color-ink)]">
          {node.name}
        </span>

        {node.model && (
          <span className="mono hidden w-28 shrink-0 truncate text-[11px] text-[var(--color-ink-3)] lg:inline">
            {node.model}
          </span>
        )}
        {node.prompt_version && (
          <span className="mono hidden w-14 shrink-0 text-[11px] text-[var(--color-ink-3)] xl:inline">
            v{node.prompt_version}
          </span>
        )}

        <span className="mono ml-auto hidden w-28 shrink-0 text-right text-[11px] text-[var(--color-ink-3)] sm:inline">
          {node.input_tokens.toLocaleString()} / {node.output_tokens.toLocaleString()}
        </span>
        <span className="mono w-16 shrink-0 text-right text-[11px] text-[var(--color-ink-2)]">
          {node.latency_ms ?? 0}ms
        </span>

        {hasDetail ? (
          <button
            onClick={() => setOpen(!open)}
            aria-label={open ? `收起 ${node.name}` : `展开 ${node.name}`}
            aria-expanded={open}
            className="w-5 shrink-0 rounded text-[11px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-5 shrink-0" />
        )}
      </div>

      {/* 相对父 span 的时间条。tooltip 给的是它占整条 trace 的比重 */}
      <div className="mx-2 mb-1.5 h-[3px] overflow-hidden rounded-full bg-[var(--color-track)]">
        <div
          className="h-full rounded-full"
          style={{
            marginLeft: `${offsetPct}%`,
            width: `${widthPct}%`,
            background: kind.color,
            opacity: 0.85,
          }}
          title={total > 0 ? `占整条 trace ${(((end - start) / total) * 100).toFixed(0)}%` : undefined}
        />
      </div>

      {open && (
        <div className="mx-2 mb-2 space-y-2.5 rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg-3)] p-3">
          {node.error && (
            <p className="text-[12px] text-[#93392f]">{node.error}</p>
          )}
          <EvaluationCard node={node} />
          <JsonBlock label="attributes" value={node.attributes} />
          <JsonBlock label="input" value={node.input} />
          <JsonBlock label="output" value={node.output} />
        </div>
      )}

      {children.length > 0 && (
        <div className="ml-3 border-l border-[var(--color-line)] pl-3">
          {children.map((c) => (
            <SpanRow
              key={c.id}
              node={c}
              parentStart={start}
              parentEnd={end}
              total={total}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** 评估结果从用例 span 的 output 里挖出来单独渲染，比埋在 JSON 里好找。 */
function readEvaluation(node: SpanNode): Record<string, unknown> | null {
  const out = node.output as { evaluation?: Record<string, unknown> } | null;
  return out && typeof out === "object" && out.evaluation ? out.evaluation : null;
}

function EvaluationCard({ node }: { node: SpanNode }) {
  const data = readEvaluation(node);
  if (!data) return null;
  const action = String(data.next_action ?? "");
  const dims = [
    ["深度", data.technical_depth],
    ["表达", data.clarity],
    ["有据", data.evidence],
    ["切题", data.relevance],
  ] as const;

  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">本轮评估</Badge>
        {dims.map(([label, v]) => (
          <span key={label} className="text-[11px] text-[var(--color-ink-3)]">
            {label}
            <span className="mono ml-1 text-[var(--color-ink-2)]">{String(v)}</span>
          </span>
        ))}
        <Badge tone="custom">{ACTION_LABELS[action] ?? action}</Badge>
      </div>
      <p className="muted mt-2 text-[12px]">{String(data.summary ?? "")}</p>
      <p className="mt-1.5 border-l-2 border-[var(--color-k-custom)]/40 pl-2.5 text-[12px] leading-relaxed text-[var(--color-ink-2)]">
        {String(data.follow_up_reason ?? "")}
      </p>
    </div>
  );
}
