import type { components, paths } from "./schema";

export type BackendPaths = paths;
export type User = components["schemas"]["UserResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type ChatMessage = components["schemas"]["ChatMessage"];

export type StreamEvent =
  | { type: "text_delta"; text: string }
  | {
      type: "usage";
      input_tokens: number | null;
      output_tokens: number | null;
      cached_input_tokens: number | null;
    }
  | { type: "done"; finish_reason: string | null }
  | { type: "error"; code: string; message: string; retryable: boolean };

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/$/, "");
const accessTokenKey = "month3.access_token";

type ErrorInfo = {
  code?: string;
  message?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function getErrorInfo(body: unknown): ErrorInfo {
  if (!isRecord(body)) {
    return {};
  }

  const detail = body.detail;
  if (isRecord(detail)) {
    return {
      code: typeof detail.code === "string" ? detail.code : undefined,
      message: typeof detail.message === "string" ? detail.message : undefined,
    };
  }

  if (typeof detail === "string") {
    return { message: detail };
  }

  if (Array.isArray(detail)) {
    return { message: "请求参数不合法" };
  }

  return {
    code: typeof body.code === "string" ? body.code : undefined,
    message: typeof body.msg === "string" ? body.msg : undefined,
  };
}

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, info: ErrorInfo = {}) {
    super(info.message || "请求失败（HTTP " + status + "）");
    this.name = "ApiRequestError";
    this.status = status;
    this.code = info.code;
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

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", "Bearer " + token);
  }

  const response = await fetch(apiBaseUrl + path, { ...init, headers });
  const body = await response.json().catch(() => undefined);

  if (!response.ok) {
    throw new ApiRequestError(response.status, getErrorInfo(body));
  }

  return body as T;
}

export function getJson<T = unknown>(path: string, token?: string): Promise<T> {
  return requestJson<T>(path, {}, token);
}

export function postJson<T = unknown>(
  path: string,
  body: unknown,
  token?: string,
): Promise<T> {
  return requestJson<T>(
    path,
    { method: "POST", body: JSON.stringify(body) },
    token,
  );
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
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({ messages }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => undefined);
    throw new ApiRequestError(response.status, getErrorInfo(body));
  }

  if (!response.body) {
    throw new Error("服务器没有返回流式内容");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const result = await reader.read();
      buffer += decoder.decode(result.value || new Uint8Array(), {
        stream: !result.done,
      });

      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim()) {
          yield JSON.parse(line) as StreamEvent;
        }
      }

      if (result.done) {
        break;
      }
    }

    if (buffer.trim()) {
      yield JSON.parse(buffer) as StreamEvent;
    }
  } finally {
    reader.releaseLock();
  }
}

export function isAuthError(error: unknown): boolean {
  return (
    error instanceof ApiRequestError &&
    (error.status === 401 || error.status === 403)
  );
}