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
  return <As className={`panel ${className}`}>{children}</As>;
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
    <div className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
      <div className="flex items-baseline gap-2.5">
        <h2 className="text-[14px] font-semibold text-ink">{title}</h2>
        {hint && <span className="text-[12.5px] text-ink-3">{hint}</span>}
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
    "inline-flex select-none items-center justify-center gap-2 rounded-md text-[14px] font-medium " +
    "transition-[background-color,color,border-color,filter,transform] duration-150 " +
    "disabled:pointer-events-none disabled:opacity-40 active:translate-y-px";

  const variants = {
    // 金色是稀缺资源：只有主操作配得上实心。浅底上用更亮的那档金色，
    // 配深色字，对比才够
    primary:
      "bg-accent-solid px-4 py-2.5 text-accent-ink " +
      "shadow-[inset_0_1px_0_rgb(255_255_255/0.35),0_8px_18px_-12px_rgb(162_112_11/0.55)] " +
      "hover:brightness-[1.04]",
    ghost:
      "border border-line-2 px-4 py-2.5 text-ink-2 " +
      "transition-colors hover:border-ink-3 hover:bg-surface-2 hover:text-ink",
    text: "px-1 py-0.5 text-ink-2 hover:text-accent",
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

type Tone = "neutral" | "accent" | "agent" | "llm" | "tool" | "custom" | "retrieval" | "ok" | "warn" | "bad";

/* 暗底上标签靠「半透明底 + 同色系高亮字」，实心填充会一个个变成色块 */
const TONE_STYLES: Record<Tone, string> = {
  neutral: "bg-surface-3 text-ink-2 border-line-2",
  accent: "bg-accent-dim text-accent border-accent/30",
  agent: "bg-k-agent/12 text-k-agent border-k-agent/25",
  llm: "bg-k-llm/12 text-k-llm border-k-llm/25",
  tool: "bg-k-tool/12 text-k-tool border-k-tool/25",
  custom: "bg-k-custom/12 text-k-custom border-k-custom/25",
  retrieval: "bg-k-retrieval/12 text-k-retrieval border-k-retrieval/25",
  ok: "bg-ok/12 text-ok border-ok/25",
  warn: "bg-warn/12 text-warn border-warn/25",
  bad: "bg-bad/12 text-bad border-bad/25",
};

/** 方形小角。胶囊标签在密集界面里太吵。 */
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
      className={`inline-flex items-center rounded-sm border px-1.5 py-[3px] text-[11.5px] font-medium leading-none ${TONE_STYLES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/**
 * 状态点。不给每行套一个填充色块——一列色块会让表格变成调色板。
 * 点 + 词，扫读时靠位置和颜色，不靠边框。
 */
export function StatusDot({ tone, children }: { tone: "ok" | "bad" | "warn"; children: React.ReactNode }) {
  const color = tone === "ok" ? "var(--color-ok)" : tone === "warn" ? "var(--color-warn)" : "var(--color-bad)";
  return (
    <span className="inline-flex items-center gap-1.5 text-[12.5px]" style={{ color }}>
      <span className="size-[6px] rounded-full" style={{ background: color }} aria-hidden />
      {children}
    </span>
  );
}

/* ---------- 评分 ---------- */

const scoreColor = (v: number) =>
  v >= 4 ? "var(--color-ok)" : v >= 3 ? "var(--color-warn)" : "var(--color-bad)";

/**
 * 五格量表。数据本身就是 1–5 的离散分，所以画成五格而不是连续条——
 * 连续条会暗示精度，这里没有。
 */
export function ScoreMeter({ label, value, delay = 0 }: { label: string; value: number; delay?: number }) {
  const color = scoreColor(value);
  return (
    <div className="flex items-center gap-3">
      <span className="w-12 shrink-0 text-[12.5px] text-ink-3">{label}</span>
      <span className="flex gap-1" aria-hidden>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className="animate-rise h-[5px] w-[15px] rounded-[2px]"
            style={{
              animationDelay: `${delay + (i - 1) * 45}ms`,
              background: i <= value ? color : "var(--color-line)",
            }}
          />
        ))}
      </span>
      <span className="mono w-4 text-[13px] font-medium" style={{ color }}>
        {value}
      </span>
    </div>
  );
}

/* ---------- 展示 ---------- */

/**
 * 指标带。
 *
 * 之前是三个等宽卡片并排——那是最典型的生成式仪表盘布局，等高、等宽、
 * 等圆角、等阴影，信息密度却最低。改成一条被发丝线切开的仪表带：
 * 数字是第一层，标签贴在下面，读起来像仪表而不是像卡片。
 */
export function MetricStrip({ items }: { items: { label: string; value: string; tone?: string }[] }) {
  return (
    <div className="panel flex flex-wrap divide-y divide-line sm:flex-nowrap sm:divide-y-0">
      {items.map((it, i) => (
        <div
          key={it.label}
          className={`min-w-[7.5rem] flex-1 px-6 py-4 ${i > 0 ? "sm:border-l sm:border-line" : ""}`}
        >
          <div
            className="num text-[26px] font-semibold leading-none"
            style={it.tone ? { color: it.tone } : undefined}
          >
            {it.value}
          </div>
          <div className="mt-2 text-[12.5px] text-ink-3">{it.label}</div>
        </div>
      ))}
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
    <div className="mb-10 flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
      <div>
        <h1 className="text-[34px] font-semibold leading-[1.08] tracking-[-0.03em] text-ink">
          {title}
        </h1>
        {description && (
          <p className="mt-3 max-w-[62ch] text-[15px] leading-[1.65] text-ink-2">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
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
      className="flex items-start gap-3 rounded-lg border border-bad/30 bg-bad/[0.07] px-5 py-4"
    >
      <span className="mt-[7px] size-[6px] shrink-0 rounded-full bg-bad" aria-hidden />
      <p className="text-[14px] leading-[1.6] text-bad">{error}</p>
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed border-line-2 px-6 py-16 text-center">
      <span className="mb-5 size-[7px] rotate-45 bg-accent-solid" aria-hidden />
      <p className="text-[15px] font-medium text-ink">{title}</p>
      <p className="mt-2 max-w-[46ch] text-[13.5px] leading-[1.65] text-ink-3">{hint}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

/* ---------- JSON ---------- */

/** trace 的输入输出经常很长，默认收起，否则页面没法看。 */
export function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  if (value === null || value === undefined) return null;
  const text = JSON.stringify(value, null, 2);

  if (text.length < 48) {
    return (
      <div className="text-[12.5px]">
        <span className="text-ink-3">{label}</span>
        <span className="mono ml-2 break-all text-ink-2">{text}</span>
      </div>
    );
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* 剪贴板不可用时保持原状，不要弹 alert */
    }
  }

  return (
    <div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="text-[12.5px] text-ink-2 transition-colors hover:text-ink"
        >
          {label}
          <span className="mono ml-2 text-ink-3">{text.length.toLocaleString()} 字符</span>
        </button>
        <button
          onClick={copy}
          className="ml-auto text-[12.5px] text-ink-3 transition-colors hover:text-accent"
        >
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      {open && <pre className="code mt-2.5 max-h-96 overflow-auto px-4 py-3.5">{text}</pre>}
    </div>
  );
}

/* ---------- 链接 ---------- */

export function TraceLink({ id, className = "" }: { id: string; className?: string }) {
  return (
    <Link
      href={`/traces/${id}`}
      className={`mono inline-flex items-center rounded-xs bg-surface-2 px-1.5 py-0.5 text-[11.5px] text-ink-3 transition-colors duration-150 hover:bg-surface-3 hover:text-accent ${className}`}
    >
      {id.slice(0, 8)}
    </Link>
  );
}
