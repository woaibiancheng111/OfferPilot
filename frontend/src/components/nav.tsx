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
    <nav className="flex h-full items-stretch gap-1" aria-label="主导航">
      {NAV.map((item) => {
        // /traces 下的详情页也应该高亮 Trace
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={
              "relative flex items-center px-3 text-[14px] transition-colors duration-200 " +
              (active ? "text-ink" : "text-ink-3 hover:text-ink-2")
            }
          >
            {item.label}
            {active && (
              <span
                aria-hidden
                className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-accent"
              />
            )}
          </Link>
        );
      })}
    </nav>
  );
}
