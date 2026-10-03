"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { SpanNode, TraceDetail } from "@/lib/types";
import {
  Badge,
  Card,
  CardHeader,
  ErrorBox,
  JsonBlock,
  MetricStrip,
  PageHeader,
  ScoreMeter,
  Skeleton,
  StatusDot,
} from "@/components/ui";

/** span 类型 = 仪表盘配色。色相铺开、感知亮度接近，因此在暗底上互不压制。 */
const KIND: Record<string, { color: string; label: string; tone: "agent" | "llm" | "tool" | "custom" | "retrieval" }> = {
  custom: { color: "var(--color-k-custom)", label: "用例", tone: "custom" },
  agent: { color: "var(--color-k-agent)", label: "agent", tone: "agent" },
  llm: { color: "var(--color-k-llm)", label: "模型", tone: "llm" },
  tool: { color: "var(--color-k-tool)", label: "工具", tone: "tool" },
  retrieval: { color: "var(--color-k-retrieval)", label: "检索", tone: "retrieval" },
};

const ACTION_LABELS: Record<string, string> = {
  follow_up: "追问",
  switch_topic: "换题",
  increase_difficulty: "加难度",
};

/** 一层缩进 18px：够看清父子关系，又不至于把名字挤没。 */
const INDENT = 18;

type Flat = {
  node: SpanNode;
  depth: number;
  /** 祖先层里「下面还有兄弟」的层号，这些位置要画一条竖线穿过本行 */
  guides: number[];
  /** 本层是不是最后一个。决定竖线是继续往下，还是折成肘形收在节点上。 */
  last: boolean;
  /** 父 span 的时间窗（毫秒时间戳）。色条就画在这个窗里。 */
  from: number;
  to: number;
};

/**
 * 压平成一维列表再渲染。
 *
 * 嵌套 DOM 里没法把「本层竖线」和「子层竖线」分开画——子层一嵌套，
 * 缩进量就被 DOM 深度锁死。压平之后每行都知道自己该画哪几条引导线。
 *
 * 顺便把父 span 的时间窗带下来，这样每行都能算出自己在父窗里的偏移。
 * 根 span 的父窗就是整条 trace。
 */
function flatten(
  nodes: SpanNode[],
  from: number,
  to: number,
  depth = 0,
  guides: number[] = [],
): Flat[] {
  const out: Flat[] = [];
  nodes.forEach((node, i) => {
    const last = i === nodes.length - 1;
    out.push({ node, depth, guides, last, from, to });
    if (node.children?.length) {
      out.push(
        ...flatten(
          node.children,
          new Date(node.started_at).getTime(),
          new Date(node.ended_at ?? node.started_at).getTime(),
          depth + 1,
          last ? guides : [...guides, depth],
        ),
      );
    }
  });
  return out;
}

export function TraceView({ id }: { id: string }) {
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});

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

  const rows = useMemo(() => {
    if (!trace) return [];
    return flatten(
      trace.spans,
      new Date(trace.started_at).getTime(),
      new Date(trace.ended_at ?? trace.started_at).getTime(),
    );
  }, [trace]);
  const expandable = useMemo(
    () => rows.filter((r) => hasDetail(r.node)).map((r) => r.node.id),
    [rows],
  );
  const allOpen = expandable.length > 0 && expandable.every((sid) => open[sid]);

  if (error) return <ErrorBox error={error} />;

  if (!trace) {
    return (
      <>
        <PageHeader title="加载中" />
        <Card>
          <div className="space-y-4 p-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-3 w-2" />
                <Skeleton className="h-3.5 w-32" />
                <Skeleton className="ml-auto h-2.5 w-28" />
              </div>
            ))}
          </div>
        </Card>
      </>
    );
  }

  const total = trace.latency_ms ?? 0;
  const slowest = rows.reduce<Flat | null>(
    (best, r) => ((r.node.latency_ms ?? 0) > (best?.node.latency_ms ?? -1) ? r : best),
    null,
  );

  return (
    <>
      <div className="mb-8">
        <Link
          href="/traces"
          className="text-[12.5px] text-ink-3 transition-colors duration-150 hover:text-ink"
        >
          所有 trace
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-ink">
            {trace.name}
          </h1>
          <StatusDot tone={trace.status === "ok" ? "ok" : "bad"}>{trace.status}</StatusDot>
          {trace.user_id && <span className="text-[13px] text-ink-3">{trace.user_id}</span>}
        </div>
        <p className="mono mt-3 text-[12px] text-ink-3">{trace.id}</p>
      </div>

      <div className="mb-8">
        <MetricStrip
          items={[
            { label: "总 tokens", value: trace.total_tokens.toLocaleString() },
            { label: "总耗时", value: `${(total / 1000).toFixed(2)}s` },
            { label: "span 数", value: String(rows.length) },
            {
              label: "最慢的 span",
              value: slowest?.node.latency_ms ? `${slowest.node.latency_ms}ms` : "—",
              tone: "var(--color-warn)",
            },
          ]}
        />
      </div>

      <Card>
        <CardHeader
          title="调用树"
          right={
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              {Object.entries(KIND).map(([k, v]) => (
                <span key={k} className="flex items-center gap-1.5 text-[12px] text-ink-3">
                  <span className="size-[7px] rounded-[2px]" style={{ background: v.color }} />
                  {v.label}
                </span>
              ))}
              <button
                onClick={() =>
                  setOpen(allOpen ? {} : Object.fromEntries(expandable.map((s) => [s, true])))
                }
                className="text-[12px] text-ink-3 transition-colors hover:text-accent"
              >
                {allOpen ? "全部收起" : "全部展开"}
              </button>
            </div>
          }
        />

        <p className="px-6 pt-5 text-[12.5px] leading-[1.6] text-ink-3">
          色条的横向位置和长度都相对父 span 的时间窗，所以越深的层放得越满。
        </p>

        <ul className="px-3 py-3">
          {rows.map((row) => (
            <SpanRow
              key={row.node.id}
              row={row}
              total={total}
              open={!!open[row.node.id]}
              onToggle={() =>
                setOpen((prev) => ({ ...prev, [row.node.id]: !prev[row.node.id] }))
              }
            />
          ))}
        </ul>
      </Card>
    </>
  );
}

function hasDetail(node: SpanNode): boolean {
  return node.input !== null || node.output !== null || Object.keys(node.attributes).length > 0;
}

function SpanRow({
  row,
  total,
  open,
  onToggle,
}: {
  row: Flat;
  total: number;
  open: boolean;
  onToggle: () => void;
}) {
  const { node, depth, guides, last, from, to } = row;
  const kind = KIND[node.kind] ?? {
    color: "var(--color-k-custom)",
    label: node.kind,
    tone: "custom" as const,
  };
  const detailed = hasDetail(node);

  const start = new Date(node.started_at).getTime();
  const end = new Date(node.ended_at ?? node.started_at).getTime();
  const ms = Math.max(end - start, 0);
  // 时间为 0 的 span 仍参与定位，但画不出宽度，压成一根竖线标记它的位置
  const collapsed = ms === 0;

  const window = Math.max(to - from, 1);
  const offset = clamp(((start - from) / window) * 100);
  const width = clamp((ms / window) * 100);
  const share = (ms / (total || 1)) * 100;

  return (
    <li className="relative">
      {/* 祖先层穿透本行的竖线 */}
      {guides.map((g) => (
        <span
          key={g}
          aria-hidden
          className="absolute top-0 h-full w-px bg-line"
          style={{ left: g * INDENT + 8 }}
        />
      ))}
      {/* 本层：折成肘形收进节点，兄弟还在下面就继续往下画 */}
      {depth > 0 && (
        <>
          {!last && (
            <span
              aria-hidden
              className="absolute w-px bg-line"
              style={{ left: depth * INDENT + 8, top: 18, bottom: 0 }}
            />
          )}
          <span
            aria-hidden
            className="absolute size-[9px] rounded-br-[2px] border-r border-b border-line"
            style={{ left: depth * INDENT + 8, top: 9 }}
          />
        </>
      )}

      <div
        className={
          "group relative flex flex-col gap-2 rounded-md py-2 pr-3 transition-colors duration-150 " +
          "hover:bg-surface-2 sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)_auto] sm:items-center sm:gap-5 " +
          (open ? "bg-surface-2" : "")
        }
      >
        {/* 节点跨在父层引导线上，所以圆点中心对齐 depth*INDENT+8 */}
        <span
          aria-hidden
          className="absolute size-[11px] rounded-full border-2 border-bg"
          style={{ left: depth * INDENT + 2.5, top: 13, background: kind.color }}
        />

        <div
          className="flex min-w-0 items-center gap-3"
          style={{ paddingLeft: depth * INDENT + 22 }}
        >
          <span className="mono w-[52px] shrink-0 text-[11.5px]" style={{ color: kind.color }}>
            {node.kind}
          </span>
          <span className="truncate text-[14px] text-ink" title={node.name}>
            {node.name}
          </span>
          {node.model && (
            <span className="mono hidden shrink-0 truncate text-[11.5px] text-ink-3 lg:inline">
              {node.model}
            </span>
          )}
          {node.prompt_version && (
            <span className="mono hidden shrink-0 text-[11.5px] text-ink-3 xl:inline">
              v{node.prompt_version}
            </span>
          )}
        </div>

        {/*
          时间条。宽度不够时把耗时挪到条子末端外侧，
          绝不为了塞下文字而拉长条子——那会让读数失真。
        */}
        <div className="relative h-4 sm:h-5">
          <span aria-hidden className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line" />
          <span
            aria-hidden
            className="absolute top-1/2 h-[7px] -translate-y-1/2 rounded-[3px]"
            style={{
              left: `${offset}%`,
              width: collapsed ? "2px" : `${Math.max(width, 0.6)}%`,
              background: kind.color,
              boxShadow: `0 0 14px -4px ${kind.color}`,
            }}
            title={ms ? `占整条 trace ${share.toFixed(0)}%` : undefined}
          />
          {node.latency_ms ? (
            <DurationLabel
              inside={!collapsed && width >= 17}
              offset={offset}
              width={collapsed ? 0 : Math.max(width, 0.6)}
              ms={node.latency_ms}
            />
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-3">
          <span className="mono text-[11.5px] text-ink-3">
            {node.input_tokens.toLocaleString()} / {node.output_tokens.toLocaleString()}
          </span>
          {detailed ? (
            <button
              onClick={onToggle}
              aria-expanded={open}
              aria-label={open ? `收起 ${node.name}` : `展开 ${node.name}`}
              className="grid size-6 shrink-0 place-items-center rounded-sm text-ink-3 transition-colors hover:bg-surface-3 hover:text-ink"
            >
              <Chevron open={open} />
            </button>
          ) : (
            <span className="size-6 shrink-0" />
          )}
        </div>
      </div>

      {open && (
        <div
          className="animate-rise mb-2 ml-8 space-y-3 rounded-md border border-line bg-surface-2/50 p-4"
          style={{ marginLeft: depth * INDENT + 22 }}
        >
          {node.error && <p className="text-[13px] text-bad">{node.error}</p>}
          <EvaluationBlock node={node} />
          <JsonBlock label="attributes" value={node.attributes} />
          <JsonBlock label="input" value={node.input} />
          <JsonBlock label="output" value={node.output} />
        </div>
      )}
    </li>
  );
}

function clamp(v: number) {
  return Math.min(Math.max(v, 0), 100);
}

/** 耗时文字：条子够宽就压在条子里，否则跟在条子末端，两种都不改动条的宽度。 */
function DurationLabel({
  inside,
  offset,
  width,
  ms,
}: {
  inside: boolean;
  offset: number;
  width: number;
  ms: number;
}) {
  return (
    <span
      className={
        "mono absolute top-1/2 -translate-y-1/2 text-[10.5px] font-medium " +
        (inside ? "text-[#0f1319]" : "text-ink-3")
      }
      style={
        inside
          ? { left: `calc(${offset}% + 7px)` }
          : { left: `calc(${offset + width}% + 8px)` }
      }
    >
      {ms}ms
    </span>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <span
      aria-hidden
      className={
        "block size-[7px] border-r-[1.5px] border-b-[1.5px] border-current transition-transform duration-200 " +
        (open ? "rotate-45" : "-rotate-45")
      }
      style={{ marginTop: open ? -3 : 2 }}
    />
  );
}

/* ---------- 评估 ---------- */

const DIMS: [string, string][] = [
  ["technical_depth", "深度"],
  ["clarity", "表达"],
  ["evidence", "有据"],
  ["relevance", "切题"],
];

/** 评估结果从用例 span 的 output 里挖出来单独渲染，比埋在 JSON 里好找。 */
function readEvaluation(node: SpanNode): Record<string, unknown> | null {
  const out = node.output as { evaluation?: Record<string, unknown> } | null;
  return out && typeof out === "object" && out.evaluation ? out.evaluation : null;
}

function EvaluationBlock({ node }: { node: SpanNode }) {
  const data = readEvaluation(node);
  if (!data) return null;
  const action = String(data.next_action ?? "");
  const scores = DIMS.map(([k]) => Number(data[k] ?? 0));
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const meanColor = mean >= 4 ? "var(--color-ok)" : mean >= 3 ? "var(--color-warn)" : "var(--color-bad)";

  return (
    <div className="panel-flat p-4">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <Badge tone="accent">本轮评估</Badge>
        <span className="flex items-baseline gap-1.5">
          <span className="num text-[22px] font-semibold leading-none" style={{ color: meanColor }}>
            {mean.toFixed(1)}
          </span>
          <span className="text-[12px] text-ink-3">四维均分</span>
        </span>
        <span className="ml-auto">
          <Badge tone="custom">下一步{ACTION_LABELS[action] ?? action}</Badge>
        </span>
      </div>
      <div className="mt-4 grid gap-2.5 sm:grid-cols-2 sm:gap-x-6">
        {DIMS.map(([key, label], i) => (
          <ScoreMeter key={key} label={label} value={Number(data[key] ?? 0)} delay={i * 60} />
        ))}
      </div>
      <p className="mt-4 text-[13.5px] leading-[1.7] text-ink-2">{String(data.summary ?? "")}</p>
      <p className="mt-2 border-l-2 border-k-custom/50 pl-3 text-[13px] leading-[1.65] text-ink-3">
        {String(data.follow_up_reason ?? "")}
      </p>
    </div>
  );
}
