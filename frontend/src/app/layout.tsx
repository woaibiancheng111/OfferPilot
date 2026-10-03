import type { Metadata } from "next";
import Link from "next/link";
import { Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { NavLinks } from "@/components/nav";
import "./globals.css";

/**
 * Instrument Sans 带一条宽度轴，标题上会收窄到 92——仪器面板上的刻字感，
 * 而不是又一个圆润的 SaaS 标题。中文交给系统字，latin 才有这个性格。
 *
 * JetBrains Mono 只给真数据：trace id、token、耗时、JSON。界面文字一律不用它，
 * 等宽铺满小标签是生成式界面最容易露的破绽。
 */
const instrument = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument",
  display: "swap",
  axes: ["wdth"],
});

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
  openGraph: {
    title: "OfferPilot",
    description: "求职 Agent 与自研观测评测平台：可观测性、多 Agent 协作、LLM-as-Judge",
    type: "website",
    locale: "zh_CN",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${instrument.variable} ${jetbrains.variable}`}>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface-3 focus:px-4 focus:py-2 focus:text-sm focus:text-ink"
        >
          跳到主内容
        </a>

        <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur-xl">
          <div className="mx-auto flex h-[60px] max-w-[1440px] items-center gap-10 px-6 lg:px-10">
            <Link
              href="/"
              className="flex items-center gap-2.5 transition-opacity duration-200 hover:opacity-80"
            >
              <span className="size-[7px] rotate-45 bg-accent-solid" aria-hidden />
              <span className="text-[15px] font-semibold tracking-[-0.01em]">OfferPilot</span>
            </Link>

            <NavLinks />

            <span className="ml-auto hidden text-[12.5px] text-ink-3 sm:block">
              求职 Agent 与观测评测
            </span>
          </div>
        </header>

        <main id="main" className="mx-auto max-w-[1440px] px-6 py-10 lg:px-10 lg:py-14">
          {children}
        </main>
      </body>
    </html>
  );
}
