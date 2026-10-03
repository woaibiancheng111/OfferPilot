import Link from "next/link";
import { Button, Card } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-[38rem] py-10">
      <div className="flex items-baseline gap-4">
        <span className="num text-[56px] font-semibold leading-none text-line-2">404</span>
        <span className="size-[7px] rotate-45 bg-accent" aria-hidden />
      </div>

      <h1 className="mt-7 text-[30px] font-semibold leading-tight tracking-[-0.02em] text-ink">
        这个页面不存在
      </h1>
      <p className="mt-3 text-[15px] leading-[1.65] text-ink-2">
        链接可能过期了，或者地址拼错了。回到面试页跑一轮，或者去 trace 列表看看最近发生了什么。
      </p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/">
          <Button>去面试</Button>
        </Link>
        <Link href="/traces">
          <Button variant="ghost">看 trace</Button>
        </Link>
      </div>

      <Card className="mt-12">
        <div className="p-6">
          <p className="text-[14px] font-medium text-ink">如果这两个页面都打不开，先看后端</p>
          <pre className="code mt-3 overflow-x-auto px-4 py-3.5">
            cd backend
            .venv\Scripts\python.exe -m uvicorn app.main:app --port 18088
          </pre>
        </div>
      </Card>
    </div>
  );
}
