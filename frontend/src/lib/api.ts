import type {
  JDAnalysis,
  ParseJDResponse,
  SessionResponse,
  TraceDetail,
  TraceList,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:18088";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** 后端把错误包成 {detail: string} 或 FastAPI 校验错误的数组。 */
function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length > 0) {
      return d
        .map((item) => {
          const e = item as { loc?: unknown[]; msg?: string };
          const where = Array.isArray(e.loc) ? e.loc.slice(1).join(".") : "";
          return where ? `${where}: ${e.msg ?? ""}` : (e.msg ?? "");
        })
        .join("；");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      `连不上后端 ${API_BASE}。确认服务已启动：cd backend && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 18088`,
      0,
    );
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(detailOf(body, `HTTP ${res.status}`), res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  parseJD: (jdText: string) =>
    request<ParseJDResponse>("/api/jd/parse", {
      method: "POST",
      body: JSON.stringify({ jd_text: jdText }),
    }),

  startInterview: (jd: JDAnalysis, userId: string, resumeText?: string) =>
    request<SessionResponse>("/api/interview/start", {
      method: "POST",
      body: JSON.stringify({
        jd,
        user_id: userId,
        resume_text: resumeText?.trim() ? resumeText : null,
      }),
    }),

  submitAnswer: (sessionId: string, answer: string) =>
    request<SessionResponse>(`/api/interview/${sessionId}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),

  listTraces: (limit = 20, offset = 0) =>
    request<TraceList>(`/api/traces?limit=${limit}&offset=${offset}`),

  getTrace: (id: string) => request<TraceDetail>(`/api/traces/${id}`),
};
