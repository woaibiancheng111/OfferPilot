"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { TraceList } from "@/lib/types";
import { Badge, ErrorBox, Panel } from "@/components/ui";

export default function TracesPage() {
  const [offset, setOffset] = useState(0);
  // 结果带上它是第几页的结果，翻页期间不展示上一页的数据（避免闪一下旧内容）
  const [result, setResult] = useState<{
    offset: number;
    data: TraceList | null;
    error: string | null;
  } | null>(null);
  const limit = 20;

  useEffect(() => {
    let alive = true;
    api
      .listTraces(limit, offset)
      .then((d) => alive && setResult({ offset, data: d, error: null }))
      .catch((e) =>
        alive && setResult({ offset, data: null, error: e instanceof ApiError ? e.message : String(e) }),
      );
    return () => {
      alive = false;
    };
  }, [offset]);

  const current = result?.offset === offset ? result : null;
  const loading = current === null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Trace</h1>
        <p className="text-xs text-[var(--color-ink-faint)]">
          一次 HTTP 请求 = 一条 trace，点进去看 span 树、耗时和 token
        </p>
      </div>

      <ErrorBox error={error} />

      <Panel>
        {loading && <p className="text-sm text-[var(--color-ink-faint)]">加载中…</p>}
        {data && !loading && data.items.length === 0 && (
          <p className="text-sm text-[var(--color-ink-faint)]">
            还没有 trace。先去面试页跑一次吧。
          </p>
        )}
        {data && data.items.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-line)] text-left text-xs text-[var(--color-ink-faint)]">
                <th className="pb-2 font-normal">trace</th>
                <th className="pb-2 font-normal">用户</th>
                <th className="pb-2 font-normal">状态</th>
                <th className="pb-2 text-right font-normal">tokens</th>
                <th className="pb-2 text-right font-normal">耗时</th>
                <th className="pb-2 text-right font-normal">时间</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((t) => (
                <tr key={t.id} className="border-b border-[var(--color-line)]/40">
                  <td className="py-2">
                    <Link
                      href={`/traces/${t.id}`}
                      className="mono text-[var(--color-accent)] hover:underline"
                    >
                      {t.name}
                    </Link>
                    <span className="mono ml-2 text-xs text-[var(--color-ink-faint)]">
                      {t.id.slice(0, 8)}
                    </span>
                  </td>
                  <td className="py-2 text-[var(--color-ink-dim)]">{t.user_id ?? "—"}</td>
                  <td className="py-2">
                    <Badge tone={t.status === "ok" ? "ok" : "bad"}>{t.status}</Badge>
                  </td>
                  <td className="py-2 text-right mono text-[var(--color-ink-dim)]">
                    {t.total_tokens}
                  </td>
                  <td className="py-2 text-right mono text-[var(--color-ink-dim)]">
                    {t.latency_ms ?? "—"} ms
                  </td>
                  <td className="py-2 text-right text-xs text-[var(--color-ink-faint)]">
                    {new Date(t.started_at).toLocaleString("zh-CN")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data && (
          <div className="mt-3 flex items-center justify-between text-xs">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="text-[var(--color-ink-dim)] disabled:opacity-30"
            >
              ← 上一页
            </button>
            <span className="text-[var(--color-ink-faint)]">
              {offset + 1} – {offset + data.items.length} / 共 {data.total}
            </span>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={offset + data.items.length >= data.total}
              className="text-[var(--color-ink-dim)] disabled:opacity-30"
            >
              下一页 →
            </button>
          </div>
        )}
      </Panel>
    </div>
  );
}
