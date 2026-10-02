import Link from "next/link";
import { Button, Card, EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-[32rem] py-16">
      <p className="mono text-[11px] tracking-[0.2em] text-[var(--color-ink-3)]">404</p>
      <h1 className="mt-3 text-[28px] font-semibold tracking-[-0.02em]">这个页面不存在</h1>
      <p className="muted mt-3 text-sm">
        链接可能过期了，或者地址拼错了。回到面试页跑一轮，或者去 trace 列表看看最近发生了什么。
      </p>
      <div className="mt-7 flex gap-3">
        <Link href="/">
          <Button>去面试</Button>
        </Link>
        <Link href="/traces">
          <Button variant="ghost">看 trace</Button>
        </Link>
      </div>
      <Card className="mt-10">
        <EmptyState
          title="也可以检查一下后端是否在跑"
          hint="cd backend && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 18088"
        />
      </Card>
    </div>
  );
}
