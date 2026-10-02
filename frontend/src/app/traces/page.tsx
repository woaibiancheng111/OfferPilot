"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { TraceList } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorBox, PageHeader, Skeleton } from "@/components/ui";

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
        description="一次 HTTP 请求 = 一条 trace。点进去看 agent / llm / tool 的调用树、耗时和 token。"
      />

      <div className="space-y-4">
        <ErrorBox error={current?.error ?? null} />

        {loading ? (
          <Card>
            <div className="space-y-3 p-5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-16" />
                  <Skeleton className="ml-auto h-3 w-12" />
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
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-line)] text-left">
                      <Th>trace</Th>
                      <Th>用户</Th>
                      <Th>状态</Th>
                      <Th className="text-right">tokens</Th>
                      <Th className="text-right">耗时</Th>
                      <Th className="text-right">时间</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((t) => (
                      <tr
                        key={t.id}
                        className="border-b border-[var(--color-line)]/50 transition-colors duration-150 last:border-0 hover:bg-[var(--color-bg-3)]/60"
                      >
                        <td className="px-5 py-3">
                          <Link
                            href={`/traces/${t.id}`}
                            className="text-[13px] text-[var(--color-ink)] transition-colors hover:text-[var(--color-accent)]"
                          >
                            {t.name}
                          </Link>
                          <span className="mono ml-2 text-[11px] text-[var(--color-ink-3)]">
                            {t.id.slice(0, 8)}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-[13px] text-[var(--color-ink-2)]">
                          {t.user_id ?? "—"}
                        </td>
                        <td className="px-5 py-3">
                          <Badge tone={t.status === "ok" ? "ok" : "bad"}>{t.status}</Badge>
                        </td>
                        <td className="mono px-5 py-3 text-right text-[13px] text-[var(--color-ink-2)]">
                          {t.total_tokens.toLocaleString()}
                        </td>
                        <td className="mono px-5 py-3 text-right text-[13px] text-[var(--color-ink-2)]">
                          {t.latency_ms === null ? "—" : `${(t.latency_ms / 1000).toFixed(1)}s`}
                        </td>
                        <td className="mono px-5 py-3 text-right text-[11px] text-[var(--color-ink-3)]">
                          {new Date(t.started_at).toLocaleString("zh-CN", {
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              <div className="flex items-center justify-between text-[11px] text-[var(--color-ink-3)]">
                <PageButton disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
                  ← 更早
                </PageButton>
                <span className="mono">
                  {offset + 1}–{offset + data.items.length} / 共 {data.total}
                </span>
                <PageButton
                  disabled={offset + data.items.length >= data.total}
                  onClick={() => setOffset(offset + LIMIT)}
                >
                  更新 →
                </PageButton>
              </div>
            </>
          )
        )}
      </div>
    </>
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
    <th className={`label px-5 py-2.5 font-medium ${className}`} scope="col">
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
      className="rounded-[var(--radius-sm)] px-2.5 py-1.5 text-[11px] text-[var(--color-ink-2)] transition-colors duration-150 hover:bg-[var(--color-bg-3)] hover:text-[var(--color-ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)] disabled:pointer-events-none disabled:opacity-30"
    >
      {children}
    </button>
  );
}
