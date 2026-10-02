"use client";

import Link from "next/link";
import { useState } from "react";

/* ---------- 容器 ---------- */

export function Card({
  children,
  className = "",
  as: As = "section",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "section" | "article" | "aside" | "div";
}) {
  return <As className={`card ${className}`}>{children}</As>;
}

export function CardHeader({
  title,
  hint,
  right,
}: {
  title: string;
  hint?: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-[var(--color-line)] px-5 py-3.5">
      <div className="flex items-baseline gap-3">
        <h2 className="text-[13px] font-semibold tracking-wide">{title}</h2>
        {hint && <span className="label">{hint}</span>}
      </div>
      {right}
    </div>
  );
}

/* ---------- 按钮 ---------- */

type ButtonProps = {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "text";
  type?: "button" | "submit";
  className?: string;
};

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
  className = "",
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-[var(--radius-sm)] text-sm font-medium " +
    "transition-[background-color,color,transform,box-shadow] duration-150 ease-out " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)] " +
    "disabled:pointer-events-none disabled:opacity-40 active:scale-[0.98]";

  const variants = {
    primary:
      "bg-[var(--color-accent)] px-3.5 py-2 text-[#0a0b0e] font-semibold " +
      "shadow-[0_1px_0_rgb(255_255_255/0.15)_inset] hover:brightness-110",
    ghost:
      "px-3 py-2 text-[var(--color-ink-2)] border border-[var(--color-line)] " +
      "hover:border-[var(--color-line-2)] hover:bg-[var(--color-bg-3)] hover:text-[var(--color-ink)]",
    text: "px-1.5 py-1 text-[var(--color-ink-2)] hover:text-[var(--color-accent)]",
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

/* ---------- 标签 ---------- */

type Tone = "neutral" | "accent" | "agent" | "llm" | "tool" | "custom" | "ok" | "warn" | "bad";

const TONE_STYLES: Record<Tone, string> = {
  neutral: "bg-[var(--color-bg-3)] text-[var(--color-ink-2)] border-[var(--color-line)]",
  accent: "bg-[var(--color-accent-dim)] text-[var(--color-accent)] border-transparent",
  agent: "bg-[#8e86d4]/12 text-[#a79fe0] border-transparent",
  llm: "bg-[#5b9bd5]/12 text-[#79b2e2] border-transparent",
  tool: "bg-[#58a67e]/12 text-[#6fba92] border-transparent",
  custom: "bg-[#c2a15a]/12 text-[#d0b273] border-transparent",
  ok: "bg-[#5ba97e]/12 text-[#6fbb92] border-transparent",
  warn: "bg-[#c2a15a]/12 text-[#d0b273] border-transparent",
  bad: "bg-[#c86a62]/12 text-[#d68179] border-transparent",
};

/** 方形小角，不是胶囊。胶囊标签在密集界面里太吵。 */
export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-[5px] border px-1.5 py-[3px] text-[11px] font-medium leading-none ${TONE_STYLES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/* ---------- 评分 ---------- */

export function ScoreBar({ label, value }: { label: string; value: number }) {
  const color = value >= 4 ? "var(--color-ok)" : value >= 3 ? "var(--color-warn)" : "var(--color-bad)";
  return (
    <div className="flex items-center gap-2">
      <span className="w-10 shrink-0 text-[11px] text-[var(--color-ink-3)]">{label}</span>
      <span className="flex gap-[3px]">
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className="h-[3px] w-3.5 rounded-[1px] transition-colors duration-300"
            style={{ background: i <= value ? color : "var(--color-line)" }}
          />
        ))}
      </span>
      <span className="mono w-7 text-[11px] text-[var(--color-ink-3)]">{value}</span>
    </div>
  );
}

/* ---------- 展示 ---------- */

export function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-bg-2)] px-4 py-3">
      <div className="mono text-[22px] font-semibold leading-none tracking-tight" style={tone ? { color: tone } : undefined}>
        {value}
      </div>
      <div className="label mt-2">{label}</div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-7 flex items-end justify-between gap-6">
      <div>
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
        {description && <p className="muted mt-1.5 max-w-[62ch] text-sm">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/* ---------- 状态 ---------- */

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-[var(--radius-md)] border border-[#c86a62]/30 bg-[#c86a62]/8 px-4 py-3"
    >
      <span className="mt-[3px] size-1.5 shrink-0 rounded-full bg-[var(--color-bad)]" />
      <p className="text-sm leading-relaxed text-[#d99a94]">{error}</p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius-md)] border border-dashed border-[var(--color-line-2)] px-6 py-14 text-center">
      <p className="text-sm font-medium text-[var(--color-ink-2)]">{title}</p>
      <p className="mt-1.5 max-w-[42ch] text-xs leading-relaxed text-[var(--color-ink-3)]">{hint}</p>
    </div>
  );
}

/* ---------- JSON ---------- */

/** trace 的输入输出经常很长，默认收起，否则页面没法看。 */
export function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  if (value === null || value === undefined) return null;
  const text = JSON.stringify(value, null, 2);
  if (text.length < 48) {
    return (
      <div className="text-[11px]">
        <span className="text-[var(--color-ink-3)]">{label}</span>
        <span className="mono ml-1.5 break-all text-[var(--color-ink-2)]">{text}</span>
      </div>
    );
  }
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="text-[11px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink-2)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
      >
        {open ? "▾" : "▸"} {label} · {text.length} 字符
      </button>
      {open && (
        <pre className="mono mt-2 max-h-96 overflow-auto rounded-[var(--radius-sm)] border border-[var(--color-line)] bg-[var(--color-bg)] p-3 text-[11px] leading-relaxed text-[var(--color-ink-2)]">
          {text}
        </pre>
      )}
    </div>
  );
}

/* ---------- 链接 ---------- */

export function TraceLink({ id, className = "" }: { id: string; className?: string }) {
  return (
    <Link
      href={`/traces/${id}`}
      className={`mono text-[11px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-accent)] ${className}`}
    >
      {id.slice(0, 8)}
    </Link>
  );
}
