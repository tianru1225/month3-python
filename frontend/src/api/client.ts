export type User = {
  id: number;
  username: string;
  status: string;
  created_at: string;
};

export type TokenResponse = { access_token: string; token_type: string };

export type Project = {
  id: number;
  name: string;
  goal: string;
  current_level: string;
  deadline: string | null;
  daily_minutes: number;
  weekly_days: number;
  expected_outcome: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type MaterialUpload = {
  material_id: number;
  version_id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  version_number: number;
  original_filename: string;
  normalized_format: string;
  mime_type: string;
  size_bytes: number;
  content_hash: string;
  parse_status: string;
  uploaded_at: string;
};

export type MaterialBinding = {
  id: number;
  project_id: number;
  material_id: number;
  bound_at: string;
  unbound_at: string | null;
};

export type MaterialParse = {
  material_id: number;
  version_id: number;
  version_number: number;
  original_filename: string;
  normalized_format: string;
  parse_status: string;
  parse_job_id: string | null;
  parser_name: string | null;
  parser_version: string | null;
  content_summary: string | null;
  parsed_content_location: string | null;
  source_metadata: Record<string, unknown> | null;
  parse_error_code: string | null;
  parse_error_message: string | null;
  processed_at: string | null;
};

export type Task = {
  id: number;
  plan_version_id: number;
  position: number;
  scheduled_date: string | null;
  title: string;
  objective: string;
  instructions: string;
  steps: string[];
  estimated_minutes: number;
  deliverable: string;
  acceptance_criteria: string[];
  status: string;
  created_at: string;
  completed_at: string | null;
  prerequisites: { task_id: number; status: string }[];
  prerequisites_complete: boolean;
};

export type TodayTasks = {
  project_id: number;
  plan_version_id: number;
  target_date: string;
  tasks: Task[];
};

export type EvidenceAcceptance = {
  evidence: Record<string, unknown>;
  evaluation: {
    rule_status: string;
    rule_result: Record<string, unknown>;
    final_decision: string | null;
  };
  task_status: string;
};

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };
export type StreamEvent =
  | { type: "text_delta"; text: string }
  | { type: "usage"; input_tokens: number | null; output_tokens: number | null; cached_input_tokens: number | null }
  | { type: "done"; finish_reason: string | null }
  | { type: "error"; code: string; message: string; retryable: boolean };

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/$/, "");
const accessTokenKey = "month3.access_token";

type ErrorInfo = { code?: string; message?: string; retryable?: boolean };

function readErrorInfo(body: unknown): ErrorInfo {
  if (!body || typeof body !== "object") return {};
  const value = body as Record<string, unknown>;
  const detail = value.detail;
  if (detail && typeof detail === "object") {
    const item = detail as Record<string, unknown>;
    return {
      code: typeof item.code === "string" ? item.code : undefined,
      message: typeof item.message === "string" ? item.message : undefined,
      retryable: typeof item.retryable === "boolean" ? item.retryable : undefined,
    };
  }
  return {
    code: typeof value.code === "string" ? value.code : undefined,
    message: typeof value.msg === "string" ? value.msg : typeof detail === "string" ? detail : undefined,
  };
}

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly retryable: boolean;

  constructor(status: number, info: ErrorInfo = {}) {
    super(info.message || `请求失败（HTTP ${status}）`);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = info.code;
    this.retryable = info.retryable ?? (status >= 500 || status === 429);
  }
}

export class StreamEventError extends Error {
  readonly code: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable: boolean) {
    super(message);
    this.name = "StreamEventError";
    this.code = code;
    this.retryable = retryable;
  }
}

export function getStoredAccessToken(): string | null {
  return sessionStorage.getItem(accessTokenKey);
}

export function storeAccessToken(token: string): void {
  sessionStorage.setItem(accessTokenKey, token);
}

export function clearStoredAccessToken(): void {
  sessionStorage.removeItem(accessTokenKey);
}

async function requestJson<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(apiBaseUrl + path, { ...init, headers });
  const body = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiRequestError(response.status, readErrorInfo(body));
  return body as T;
}

export function getJson<T>(path: string, token?: string, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, { signal }, token);
}

export function postJson<T>(path: string, body: unknown, token?: string, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, { method: "POST", body: JSON.stringify(body), signal }, token);
}

export function deleteResource(path: string, token?: string, signal?: AbortSignal): Promise<void> {
  return requestJson<void>(path, { method: "DELETE", signal }, token);
}

export async function uploadMaterial(
  token: string,
  name: string,
  file: File,
  description: string,
  signal?: AbortSignal,
): Promise<MaterialUpload> {
  const form = new FormData();
  form.append("name", name);
  form.append("file", file);
  if (description.trim()) form.append("description", description.trim());
  const response = await fetch(apiBaseUrl + "/materials", {
    method: "POST",
    headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    body: form,
    signal,
  });
  const body = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiRequestError(response.status, readErrorInfo(body));
  return body as MaterialUpload;
}

export async function* streamUserChat(
  messages: ChatMessage[],
  token: string,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(apiBaseUrl + "/v1/user-chat/stream", {
    method: "POST",
    signal,
    headers: {
      Accept: "application/x-ndjson",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ messages }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => undefined);
    throw new ApiRequestError(response.status, readErrorInfo(body));
  }
  if (!response.body) throw new Error("服务端没有返回流式内容");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const result = await reader.read();
      buffer += decoder.decode(result.value || new Uint8Array(), { stream: !result.done });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as StreamEvent;
        if (event.type === "error") throw new StreamEventError(event.code, event.message, event.retryable);
        yield event;
      }
      if (result.done) break;
    }
    if (buffer.trim()) {
      const event = JSON.parse(buffer) as StreamEvent;
      if (event.type === "error") throw new StreamEventError(event.code, event.message, event.retryable);
      yield event;
    }
  } finally {
    reader.releaseLock();
  }
}