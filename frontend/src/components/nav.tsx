"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "面试" },
  { href: "/traces", label: "Trace" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1">
      {NAV.map((item) => {
        // /traces 下的详情页也应该高亮 Trace
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={
              "rounded-[var(--radius-sm)] px-3 py-1.5 text-sm transition-colors duration-150 " +
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)] " +
              (active
                ? "bg-[var(--color-bg-3)] text-[var(--color-ink)]"
                : "text-[var(--color-ink-3)] hover:bg-[var(--color-bg-3)]/60 hover:text-[var(--color-ink-2)]")
            }
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
