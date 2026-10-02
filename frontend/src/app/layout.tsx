import type { Metadata } from "next";
import Link from "next/link";
import { Geist, JetBrains_Mono } from "next/font/google";
import { NavLinks } from "@/components/nav";
import "./globals.css";

/**
 * Geist 用于界面，JetBrains Mono 用于数据。
 * 界面里全是 trace id、token 数、模型名，等宽字体的辨识度和表格数字
 * 在这种界面里比默认字体强得多。
 */
const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "OfferPilot",
    template: "%s · OfferPilot",
  },
  description: "求职 Agent 与自研观测评测平台：可观测性、多 Agent 协作、LLM-as-Judge",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${geist.variable} ${jetbrains.variable}`}>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-[var(--color-bg-3)] focus:px-3 focus:py-2 focus:text-sm"
        >
          跳到主内容
        </a>

        <header className="sticky top-0 z-20 border-b border-[var(--color-line)] bg-[var(--color-bg)]/90 backdrop-blur-xl">
          <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-8 px-6 lg:px-10">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="grid size-6 place-items-center rounded-[7px] bg-[var(--color-accent)]/15 text-[13px] font-semibold text-[var(--color-accent)]">
                O
              </span>
              <span className="text-[15px] font-semibold tracking-tight">OfferPilot</span>
            </Link>

            <NavLinks />

            <span className="label ml-auto hidden sm:block">求职 Agent · 观测评测</span>
          </div>
        </header>

        <main id="main" className="mx-auto max-w-[1400px] px-6 py-8 lg:px-10 lg:py-10">
          {children}
        </main>
      </body>
    </html>
  );
}
