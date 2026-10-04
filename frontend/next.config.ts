import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * 产出自包含的运行时目录 `.next/standalone`。
   *
   * 不开这个的话，镜像里要么塞进整个 node_modules（几百 MB），要么在
   * 容器里再跑一次 `pnpm install`——后者每次启动都要联网装依赖，
   * 服务器网络一抖服务就起不来。standalone 只带上真正用到的文件。
   *
   * 注意它只影响构建产物，本地 `pnpm dev` 照常用。
   */
  output: "standalone",

  /**
   * 关掉 dev 模式的浮层提示。
   *
   * 它会持续重挂载 React 树，表现为：自动拉数据的页面永远停在「加载中」
   * （state 被反复重置），而按钮 ref 动不动就失效。没它调试体验反而更稳。
   */
  devIndicators: false,
};

export default nextConfig;
