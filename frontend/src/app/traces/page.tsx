"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { TraceSummary, TraceList } from "@/lib/types";
import { Card, EmptyState, ErrorBox, PageHeader, Skeleton, StatusDot, TraceLink } from "@/components/ui";

const LIMIT = 20;

export default function TracesPage() {
  const [offset, setOffset] = useState(0);
  // 结果带上它属于第几页：翻页期间不展示上一页数据，避免闪一下旧内容
  const [result, setResult] = useState<{
    offset: number;
    data: TraceList | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .listTraces(LIMIT, offset)
      .then((d) => alive && setResult({ offset, data: d, error: null }))
      .catch((e) =>
        alive &&
        setResult({ offset, data: null, error: e instanceof ApiError ? e.message : String(e) }),
      );
    return () => {
      alive = false;
    };
  }, [offset]);

  const current = result?.offset === offset ? result : null;
  const loading = current === null;
  const data = current?.data ?? null;

  return (
    <>
      <PageHeader
        title="Trace"
        description="一次 HTTP 请求就是一条 trace。点进去看 agent、模型和工具的调用树、耗时与 token。"
        action={
          data && <span className="text-[12.5px] text-ink-3">共 {data.total} 条</span>
        }
      />

      <div className="space-y-5">
        <ErrorBox error={current?.error ?? null} />

        {loading ? (
          <Card>
            <div className="space-y-4 p-6">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-16" />
                  <Skeleton className="ml-auto h-2 w-16" />
                  <Skeleton className="h-3 w-16" />
                </div>
              ))}
            </div>
          </Card>
        ) : data && data.items.length === 0 ? (
          <EmptyState
            title="还没有 trace"
            hint="去面试页跑一轮，解析和问答的每一步都会记在这里。"
          />
        ) : (
          data && (
            <>
              <Card className="overflow-hidden">
                {/*
                  sticky 表头必须配 border-separate：collapse 模式下浏览器会
                  把表头当成普通行参与列宽计算，滚动时列会整体错位。
                */}
                <table className="w-full border-separate border-spacing-0 text-left">
                  <caption className="sr-only">Trace 列表，含状态、token、耗时和发生时间</caption>
                  <thead className="sticky top-[60px] z-10">
                    <tr>
                      <Th>trace</Th>
                      <Th className="hidden md:table-cell">用户</Th>
                      <Th>状态</Th>
                      <Th className="text-right">tokens</Th>
                      <Th className="text-right">耗时</Th>
                      <Th className="hidden text-right sm:table-cell">时间</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((t) => (
                      <TraceRow key={t.id} trace={t} maxLatency={maxLatency(data.items)} />
                    ))}
                  </tbody>
                </table>
              </Card>

              <div className="flex items-center justify-between">
                <PageButton disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
                  上一页
                </PageButton>
                <span className="mono text-[12px] text-ink-3">
                  {offset + 1}–{offset + data.items.length} / 共 {data.total}
                </span>
                <PageButton
                  disabled={offset + data.items.length >= data.total}
                  onClick={() => setOffset(offset + LIMIT)}
                >
                  下一页
                </PageButton>
              </div>
            </>
          )
        )}
      </div>
    </>
  );
}

/** 页内最慢的一条作为满格参考，条形长度才有可比性。 */
function maxLatency(items: TraceSummary[]): number {
  return Math.max(...items.map((i) => i.latency_ms ?? 0), 1);
}

function TraceRow({ trace, maxLatency: max }: { trace: TraceSummary; maxLatency: number }) {
  const ms = trace.latency_ms ?? 0;
  const failed = trace.status !== "ok";
  return (
    // border-separate 下边框要落在单元格上，挂在 tr 上不会画出来
    <tr className="group transition-colors duration-150 hover:bg-surface-2 [&>td]:border-b [&>td]:border-line/70 last:[&>td]:border-b-0">
      {/* 悬停时首列左侧亮一条金边，常驻 2px 透明边所以不会出现位移 */}
      <td className="border-l-2 border-transparent px-6 py-4 transition-colors duration-150 group-hover:border-accent">
        <Link
          href={`/traces/${trace.id}`}
          className="text-[15px] text-ink transition-colors duration-150 hover:text-accent"
        >
          {trace.name}
        </Link>
        <TraceLink id={trace.id} className="ml-2.5 align-middle" />
      </td>
      <td className="hidden px-6 py-4 text-[13.5px] text-ink-2 md:table-cell">
        {trace.user_id ?? "—"}
      </td>
      <td className="px-6 py-4">
        <StatusDot tone={failed ? "bad" : "ok"}>{failed ? "error" : "ok"}</StatusDot>
      </td>
      <td className="mono px-6 py-4 text-right text-[13.5px] text-ink-2">
        {trace.total_tokens.toLocaleString()}
      </td>
      {/* 长度表示快慢，颜色只区分成功与失败，不表示阈值 */}
      <td className="px-6 py-4">
        <div className="flex items-center justify-end gap-3">
          {trace.latency_ms === null ? (
            <span className="mono text-[13px] text-ink-3">—</span>
          ) : (
            <>
              <span className="hidden h-[6px] w-16 overflow-hidden rounded-full bg-line sm:block">
                <span
                  className="block h-full rounded-full transition-[width] duration-500"
                  style={{
                    width: `${Math.max((ms / max) * 100, 2)}%`,
                    background: failed ? "var(--color-bad)" : "var(--color-k-llm)",
                  }}
                />
              </span>
              <span className="mono w-14 text-right text-[13px] text-ink-2">
                {(ms / 1000).toFixed(2)}s
              </span>
            </>
          )}
        </div>
      </td>
      <td className="mono hidden px-6 py-4 text-right text-[12px] text-ink-3 sm:table-cell">
        {new Date(trace.started_at).toLocaleString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })}
      </td>
    </tr>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={`bg-surface px-6 py-3.5 text-[12.5px] font-medium text-ink-3 ${className}`}
    >
      {children}
    </th>
  );
}

function PageButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded-md border border-line-2 px-3.5 py-2 text-[12.5px] text-ink-2 transition-colors duration-150 hover:border-ink-3 hover:bg-surface-2 hover:text-ink disabled:pointer-events-none disabled:opacity-30"
    >
      {children}
    </button>
  );
}
