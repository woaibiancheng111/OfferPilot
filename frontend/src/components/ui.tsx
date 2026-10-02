"use client";

import { useState } from "react";

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] ${className}`}
    >
      {title && (
        <div className="flex items-center justify-between border-b border-[var(--color-line)] px-4 py-2">
          <h2 className="text-sm font-medium">{title}</h2>
          {right}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost";
  type?: "button" | "submit";
}) {
  const base =
    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";
  const styles =
    variant === "primary"
      ? "bg-[var(--color-accent)] text-white hover:brightness-110"
      : "border border-[var(--color-line)] text-[var(--color-ink-dim)] hover:text-[var(--color-ink)]";
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${styles}`}>
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = "dim",
}: {
  children: React.ReactNode;
  tone?: "dim" | "ok" | "warn" | "bad" | "accent";
}) {
  const tones = {
    dim: "bg-[var(--color-panel-2)] text-[var(--color-ink-dim)]",
    ok: "bg-[#1c3d24] text-[var(--color-ok)]",
    warn: "bg-[#3d3018] text-[var(--color-warn)]",
    bad: "bg-[#3d1a1a] text-[var(--color-bad)]",
    accent: "bg-[#16304d] text-[var(--color-accent)]",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs ${tones[tone]}`}>{children}</span>
  );
}

export function ScoreBar({ label, value }: { label: string; value: number }) {
  const tone = value >= 4 ? "var(--color-ok)" : value >= 3 ? "var(--color-warn)" : "var(--color-bad)";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-12 shrink-0 text-[var(--color-ink-faint)]">{label}</span>
      <span className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className="h-1.5 w-3 rounded-sm"
            style={{ background: i <= value ? tone : "var(--color-line)" }}
          />
        ))}
      </span>
      <span className="text-[var(--color-ink-dim)]">{value}/5</span>
    </div>
  );
}

/** 长 JSON 的可折叠展示。trace 的输入输出经常很大，默认收起。 */
export function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  if (value === null || value === undefined) return null;
  const text = JSON.stringify(value, null, 2);
  if (text.length < 40) {
    return (
      <div className="text-xs">
        <span className="text-[var(--color-ink-faint)]">{label}：</span>
        <span className="mono text-[var(--color-ink-dim)]">{text}</span>
      </div>
    );
  }
  return (
    <div className="text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="text-[var(--color-ink-faint)] hover:text-[var(--color-ink-dim)]"
      >
        {open ? "▾" : "▸"} {label}（{text.length} 字符）
      </button>
      {open && (
        <pre className="json mt-1 max-h-80 overflow-auto rounded bg-[var(--color-panel-2)] p-2 text-[11px] leading-relaxed text-[var(--color-ink-dim)]">
          {text}
        </pre>
      )}
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="rounded-md border border-[var(--color-bad)] bg-[#2a1414] px-3 py-2 text-sm text-[var(--color-bad)]">
      {error}
    </div>
  );
}

export function TraceLink({ id }: { id: string }) {
  return (
    <a
      href={`/traces/${id}`}
      className="mono text-xs text-[var(--color-accent)] hover:underline"
    >
      {id.slice(0, 8)}
    </a>
  );
}
