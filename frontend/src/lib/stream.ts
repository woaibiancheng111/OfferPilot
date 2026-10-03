/**
 * SSE 客户端。
 *
 * 没用 EventSource——它只支持 GET，而我们是 POST + JSON body。
 * 所以用 fetch 读 ReadableStream，自己解帧。
 */

import { API_BASE } from "./api";

export interface SseEvent<T = Record<string, unknown>> {
  id: number;
  event: string;
  data: T;
}

interface StreamOptions {
  signal?: AbortSignal;
  lastEventId?: number;
}

/** 增量解帧器：SSE 以空行分隔事件，字段格式是 `name: value`。 */
export class FrameParser {
  private buffer = "";

  push(chunk: string): SseEvent[] {
    this.buffer += chunk;
    const out: SseEvent[] = [];
    let sep: number;
    while ((sep = this.buffer.indexOf("\n\n")) >= 0) {
      const frame = this.buffer.slice(0, sep);
      this.buffer = this.buffer.slice(sep + 2);
      const parsed = parseFrame(frame);
      if (parsed) out.push(parsed);
    }
    return out;
  }
}

function parseFrame(frame: string): SseEvent | null {
  let id = 0;
  let event = "message";
  const dataLines: string[] = [];

  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue; // 注释/心跳
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "id") id = Number(value);
    else if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }

  if (!dataLines.length) return null;
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  return { id, event, data: data as Record<string, unknown> };
}

/**
 * 逐个吐出服务端事件。
 *
 * 中途断网会自动带 `Last-Event-ID` 重连一次，让服务端补发漏掉的片段——
 * 这是断线续传的实际验证点，不只是代码里有个分支。
 */
export async function* streamSse<T = Record<string, unknown>>(
  path: string,
  body: unknown,
  options: StreamOptions = {},
  attempt = 0,
): AsyncGenerator<SseEvent<T>> {
  const { signal, lastEventId } = options;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (lastEventId) headers["Last-Event-ID"] = String(lastEventId);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (attempt === 0 && lastEventId) {
      // 连不上但之前收到过内容 → 用最后的 id 重连，服务端会把漏的补回来
      yield* streamSse<T>(path, body, options, 1);
      return;
    }
    throw e;
  }

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ?? `HTTP ${res.status}`,
    );
  }
  if (!res.body) throw new Error("响应没有可读的流");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = new FrameParser();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const event of parser.push(decoder.decode(value, { stream: true }))) {
        yield event as SseEvent<T>;
      }
    }
  } catch (e) {
    if (signal?.aborted) return;
    throw e;
  } finally {
    reader.releaseLock();
  }
}
