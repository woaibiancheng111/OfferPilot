import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * 关掉 dev 模式的浮层提示。
   *
   * 它会持续重挂载 React 树，表现为：自动拉数据的页面永远停在「加载中」
   * （state 被反复重置），而按钮 ref 动不动就失效。没它调试体验反而更稳。
   */
  devIndicators: false,
};

export default nextConfig;
