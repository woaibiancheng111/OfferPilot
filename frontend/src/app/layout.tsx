import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "OfferPilot",
  description: "求职 Agent + 自研观测评测平台",
};

const NAV = [
  { href: "/", label: "面试" },
  { href: "/traces", label: "Trace" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">
        <header className="border-b border-[var(--color-line)] bg-[var(--color-panel)]">
          <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
            <span className="text-sm font-semibold tracking-wide">OfferPilot</span>
            <nav className="flex gap-4 text-sm">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-[var(--color-ink-dim)] transition-colors hover:text-[var(--color-ink)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <span className="ml-auto text-xs text-[var(--color-ink-faint)]">
              求职 Agent · 观测评测平台
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
