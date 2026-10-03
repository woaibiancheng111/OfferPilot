/**
 * 与后端 schema 对应的类型。
 *
 * 手写而不是从 OpenAPI 生成：目前只有七个接口，手写更好读也更好改。
 * 后端字段一改，这里要跟着改——这是刻意的，手写能让你注意到契约变了。
 */

export type Seniority = "实习" | "校招" | "初级" | "中级" | "高级" | "资深" | "专家" | "未知";

export interface JDAnalysis {
  company: string | null;
  role_title: string | null;
  seniority: Seniority;
  seniority_reason: string;
  business_domain: string | null;
  skills_required: string[];
  skills_nice_to_have: string[];
  responsibilities: string[];
  keywords: string[];
}

export interface ParseJDResponse extends JDAnalysis {
  attempts: number;
  input_tokens: number;
  output_tokens: number;
  trace_id: string;
}

export type Difficulty = "基础" | "进阶" | "深入";

export interface PlanTopic {
  topic: string;
  difficulty: Difficulty;
  source: "jd" | "resume" | "both";
  why: string;
}

export interface InterviewPlan {
  topics: PlanTopic[];
  focus_points: string[];
  opening: string;
}

export type NextAction = "follow_up" | "switch_topic" | "increase_difficulty";

export interface TurnEvaluation {
  technical_depth: number;
  clarity: number;
  evidence: number;
  relevance: number;
  summary: string;
  next_action: NextAction;
  follow_up_reason: string;
}

export interface Turn {
  turn_index: number;
  topic: string;
  difficulty: Difficulty;
  question: string;
  answer: string | null;
  evaluation: TurnEvaluation | null;
}

export interface SessionResponse {
  session_id: string;
  plan: InterviewPlan;
  turns: Turn[];
  finished: boolean;
  total_tokens: number;
  trace_id: string;
}

export interface TraceSummary {
  id: string;
  name: string;
  user_id: string | null;
  status: "ok" | "error";
  total_tokens: number;
  latency_ms: number | null;
  started_at: string;
}

export interface TraceList {
  items: TraceSummary[];
  total: number;
}

export interface SpanNode {
  id: string;
  parent_span_id: string | null;
  kind: "agent" | "llm" | "tool" | "retrieval" | "custom";
  name: string;
  input: unknown;
  output: unknown;
  attributes: Record<string, unknown>;
  model: string | null;
  prompt_version: string | null;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number | null;
  error: string | null;
  started_at: string;
  ended_at: string | null;
  children: SpanNode[];
}

export interface TraceDetail extends TraceSummary {
  ended_at: string | null;
  spans: SpanNode[];
}

/* ---------- 流式提交回答的事件 ---------- */

/** turn_start：上一轮的评估先到，用户不用干等 */
export interface TurnStartEvent {
  turn_index: number;
  topic: string;
  evaluation: TurnEvaluation;
}

/** question：问题增量，会来很多次 */
export interface QuestionEvent {
  delta: string;
}

/** turn_done：本轮结束 */
export interface TurnDoneEvent {
  turn_index: number;
  question: string;
  finished: boolean;
  input_tokens: number;
  output_tokens: number;
}

export interface NextTurn {
  turn_index: number;
  question: string;
  topic: string;
  difficulty: Difficulty;
}

/** session：会话最终状态 */
export interface SessionEvent {
  session_id: string;
  trace_id: string;
  finished: boolean;
  total_tokens: number;
  next_turn: NextTurn | null;
}

/** error：服务端把异常也转成事件发出来，否则前端只能等超时 */
export interface StreamErrorEvent {
  message: string;
}
