import { TraceView } from "./TraceView";

/**
 * 服务端组件负责把 params 解开，交互部分交给客户端子组件。
 *
 * 不要在客户端组件里用 `use(params)` 拿路由参数——挂起时 React 会丢弃
 * hook 状态，effect 会反复重跑（实测表现为接口被反复请求、页面卡在加载中）。
 */
export default async function TraceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <TraceView id={id} />;
}
