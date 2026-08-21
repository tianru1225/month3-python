import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  Bot,
  CircleAlert,
  Database,
  FileJson2,
  LogIn,
  LogOut,
  MessageSquare,
  RefreshCw,
  Send,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";

import {
  ApiRequestError,
  apiBaseUrl,
  clearStoredAccessToken,
  getJson,
  getStoredAccessToken,
  postJson,
  storeAccessToken,
  StreamEventError,
  streamUserChat,
  type ChatMessage,
  type TokenResponse,
  type User,
} from "./api/client";

type CheckState =
  | { kind: "checking"; detail: string }
  | { kind: "ready"; detail: string }
  | { kind: "failed"; detail: string };

type OverviewState = {
  api: CheckState;
  database: CheckState;
  contract: CheckState;
};

type ViewMessage = ChatMessage & {
  id: string;
  pending?: boolean;
  failed?: boolean;
};

type ErrorNotice = {
  title: string;
  detail: string;
  code?: string;
  status?: number;
  retryable: boolean;
  requiresLogin: boolean;
};

const checkingState: OverviewState = {
  api: { kind: "checking", detail: "正在检查" },
  database: { kind: "checking", detail: "正在检查" },
  contract: { kind: "checking", detail: "正在读取" },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function hasNestedValue(
  value: unknown,
  section: string,
  key: string,
  expected: string,
): boolean {
  return (
    isRecord(value) &&
    isRecord(value[section]) &&
    value[section][key] === expected
  );
}

function providerNotice(
  status: number | undefined,
  code: string | undefined,
  retryable: boolean,
): ErrorNotice {
  if (status === 429 || code === "LLM_RATE_LIMITED" || code === "LLM_CONCURRENCY_LIMIT") {
    return {
      title: "请求过于频繁",
      detail: "服务容量暂时不足，请稍后重新发送消息。",
      code,
      status,
      retryable,
      requiresLogin: false,
    };
  }

  if (status === 503 || code === "LLM_UPSTREAM_CONNECTION_ERROR") {
    return {
      title: "模型服务暂时不可用",
      detail: "后端暂时无法连接模型服务，请稍后再试。",
      code,
      status,
      retryable,
      requiresLogin: false,
    };
  }

  if (status === 504 || code === "LLM_REQUEST_TIMEOUT" || code === "LLM_GENERATION_TIMEOUT") {
    return {
      title: "模型响应超时",
      detail: "模型生成时间过长，请稍后重新发送消息。",
      code,
      status,
      retryable,
      requiresLogin: false,
    };
  }

  return {
    title: "模型服务返回异常",
    detail: "模型请求没有正常完成，请稍后再试。",
    code,
    status,
    retryable,
    requiresLogin: false,
  };
}

function toErrorNotice(error: unknown): ErrorNotice {
  if (error instanceof ApiRequestError) {
    if (error.code === "INVALID_CREDENTIALS") {
      return {
        title: "用户名或密码错误",
        detail: "请检查用户名和密码后重试。",
        code: error.code,
        status: error.status,
        retryable: false,
        requiresLogin: false,
      };
    }

    if (error.status === 401) {
      return {
        title: "登录状态已失效",
        detail: "请重新登录后继续使用。",
        code: error.code,
        status: error.status,
        retryable: false,
        requiresLogin: true,
      };
    }

    if (error.status === 403) {
      return {
        title: "当前用户不可用",
        detail: "当前账户没有继续访问用户工作区的权限。",
        code: error.code,
        status: error.status,
        retryable: false,
        requiresLogin: true,
      };
    }

    if (error.status === 429 || error.status >= 500) {
      return providerNotice(error.status, error.code, error.retryable);
    }

    return {
      title: "操作失败",
      detail: error.message,
      code: error.code,
      status: error.status,
      retryable: error.retryable,
      requiresLogin: false,
    };
  }

  if (error instanceof StreamEventError) {
    return providerNotice(undefined, error.code, error.retryable);
  }

  return {
    title: "请求失败",
    detail: error instanceof Error ? error.message : "页面无法完成这次请求。",
    retryable: false,
    requiresLogin: false,
  };
}

function errorDetail(error: unknown): string {
  const notice = toErrorNotice(error);
  return notice.status
    ? notice.title + "（HTTP " + notice.status + "）"
    : notice.title;
}

function newId(): string {
  return crypto.randomUUID();
}

function requestMessages(messages: ViewMessage[]): ChatMessage[] {
  return messages.map((message) => ({
    role: message.role,
    content: message.content,
  }));
}

async function loadApiState(): Promise<CheckState> {
  const body = await getJson("/health");
  if (!hasNestedValue(body, "data", "status", "ok")) {
    throw new Error("健康响应格式不匹配");
  }
  return { kind: "ready", detail: "FastAPI 在线" };
}

async function loadDatabaseState(): Promise<CheckState> {
  const body = await getJson("/debug/db-ping");
  if (!hasNestedValue(body, "data", "database", "ok")) {
    throw new Error("数据库响应格式不匹配");
  }
  return { kind: "ready", detail: "PostgreSQL 可用" };
}

async function loadContractState(): Promise<CheckState> {
  const body = await getJson("/openapi.json");
  if (!isRecord(body) || !isRecord(body.paths)) {
    throw new Error("OpenAPI 响应格式不匹配");
  }
  return {
    kind: "ready",
    detail: Object.keys(body.paths).length + " 条路径",
  };
}

export default function App() {
  const [overview, setOverview] = useState<OverviewState>(checkingState);
  const [updatedAt, setUpdatedAt] = useState("-");
  const [authReady, setAuthReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authMessage, setAuthMessage] = useState("");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ViewMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [retryText, setRetryText] = useState<string | null>(null);
  const [chatError, setChatError] = useState<ErrorNotice | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ViewMessage[]>([]);

  const refresh = useCallback(async () => {
    setOverview(checkingState);
    const [api, database, contract] = await Promise.allSettled([
      loadApiState(),
      loadDatabaseState(),
      loadContractState(),
    ]);

    setOverview({
      api:
        api.status === "fulfilled"
          ? api.value
          : { kind: "failed", detail: errorDetail(api.reason) },
      database:
        database.status === "fulfilled"
          ? database.value
          : { kind: "failed", detail: errorDetail(database.reason) },
      contract:
        contract.status === "fulfilled"
          ? contract.value
          : { kind: "failed", detail: errorDetail(contract.reason) },
    });
    setUpdatedAt(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
  }, []);

  useEffect(() => {
    void refresh();
    const storedToken = getStoredAccessToken();

    if (!storedToken) {
      setAuthReady(true);
      return;
    }

    setToken(storedToken);
    void getJson<User>("/users/me", storedToken)
      .then(setUser)
      .catch((error) => {
        clearStoredAccessToken();
        setToken(null);
        const notice = toErrorNotice(error);
        if (notice.requiresLogin) {
          setAuthMessage(notice.title + "，请重新登录");
        }
      })
      .finally(() => setAuthReady(true));
  }, [refresh]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const logout = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    clearStoredAccessToken();
    setToken(null);
    setUser(null);
    setMessages([]);
    setRetryText(null);
    setChatError(null);
  }, []);

  const submitAuth = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthBusy(true);
    setAuthMessage("");

    try {
      if (authMode === "register") {
        await postJson<User>("/users", { username, password });
      }

      const login = await postJson<TokenResponse>("/auth/login", {
        username,
        password,
      });
      const profile = await getJson<User>("/users/me", login.access_token);

      storeAccessToken(login.access_token);
      setToken(login.access_token);
      setUser(profile);
      setPassword("");
      setAuthMessage("");
    } catch (error) {
      const notice = toErrorNotice(error);
      setAuthMessage(notice.title + "：" + notice.detail);
    } finally {
      setAuthBusy(false);
    }
  };

  const runStream = useCallback(
    async (prompt: string, history: ChatMessage[]) => {
      if (!token) {
        return;
      }

      const userMessage: ViewMessage = {
        id: newId(),
        role: "user",
        content: prompt,
      };
      const assistantId = newId();
      const assistantMessage: ViewMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        pending: true,
      };

      setMessages((current) => [...current, userMessage, assistantMessage]);
      setStreaming(true);
      setRetryText(null);
      setChatError(null);

      const controller = new AbortController();
      controllerRef.current = controller;

      try {
        for await (const event of streamUserChat(
          [...history, { role: "user", content: prompt }],
          token,
          controller.signal,
        )) {
          if (event.type === "text_delta") {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: message.content + event.text }
                  : message,
              ),
            );
          } else if (event.type === "done") {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, pending: false }
                  : message,
              ),
            );
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: "本次生成已取消",
                    pending: false,
                  }
                : message,
            ),
          );
        } else {
          const notice = toErrorNotice(error);
          setChatError(notice);
          setRetryText(prompt);

          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: notice.detail,
                    pending: false,
                    failed: true,
                  }
                : message,
            ),
          );

          if (notice.requiresLogin) {
            logout();
            setAuthMessage(notice.title + "，请重新登录");
          }
        }
      } finally {
        setStreaming(false);
        controllerRef.current = null;
      }
    },
    [logout, token],
  );

  const sendMessage = () => {
    const prompt = draft.trim();
    if (!prompt || streaming || !token) {
      return;
    }

    void runStream(prompt, requestMessages(messagesRef.current));
    setDraft("");
  };

  const retry = () => {
    if (!retryText || streaming) {
      return;
    }

    const base = messagesRef.current.slice(0, -2);
    setMessages(base);
    setRetryText(null);
    setChatError(null);
    void runStream(retryText, requestMessages(base));
  };

  if (!authReady) {
    return <div className="loading-screen">正在恢复登录状态</div>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">知</span>
          <div>
            <strong>知行证据</strong>
            <span>AI 学习平台</span>
          </div>
        </div>
        <nav aria-label="主导航">
          <div className="nav-current">
            <MessageSquare size={18} aria-hidden="true" />
            <span>{user ? "用户对话" : "登录与服务"}</span>
          </div>
        </nav>
        <div className="sidebar-foot">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>Frontend-P3</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <span className="section-label">用户工作区</span>
            <h1>{user ? "你好，" + user.username : "进入学习工作区"}</h1>
          </div>
          <div className="topbar-actions">
            {user && (
              <span className="user-status">
                <UserRound size={16} />{user.status}
              </span>
            )}
            {user && (
              <button className="text-button" type="button" onClick={logout}>
                <LogOut size={16} />退出
              </button>
            )}
            <button
              className="icon-button"
              type="button"
              onClick={() => void refresh()}
              title="重新检查服务"
            >
              <RefreshCw size={18} aria-hidden="true" />
              <span className="sr-only">重新检查服务</span>
            </button>
          </div>
        </header>

        <section className="summary" aria-labelledby="summary-title">
          <div>
            <p className="eyebrow">真实后端联调</p>
            <h2 id="summary-title">
              从身份认证到用户对话，先跑通一条真实链路。
            </h2>
          </div>
          <div className="summary-meta">
            <span>同源 API</span>
            <code>{apiBaseUrl}</code>
            <small>更新于 {updatedAt}</small>
          </div>
        </section>

        <section className="status-grid" aria-label="服务检查结果">
          <StatusCard icon={<Activity size={21} />} title="应用接口" state={overview.api} tone="green" />
          <StatusCard icon={<Database size={21} />} title="数据连接" state={overview.database} tone="amber" />
          <StatusCard icon={<FileJson2 size={21} />} title="接口契约" state={overview.contract} tone="blue" />
        </section>

        {user ? (
          <ChatPanel
            draft={draft}
            messages={messages}
            streaming={streaming}
            retryText={retryText}
            chatError={chatError}
            onDraftChange={setDraft}
            onSend={sendMessage}
            onCancel={() => controllerRef.current?.abort()}
            onRetry={retry}
          />
        ) : (
          <AuthPanel
            mode={authMode}
            username={username}
            password={password}
            busy={authBusy}
            message={authMessage}
            onModeChange={(mode) => {
              setAuthMode(mode);
              setAuthMessage("");
            }}
            onUsernameChange={setUsername}
            onPasswordChange={setPassword}
            onSubmit={submitAuth}
          />
        )}

        <section className="contract-band" aria-labelledby="contract-title">
          <div>
            <p className="eyebrow">FastAPI</p>
            <h2 id="contract-title">接口契约</h2>
            <p className="supporting-copy">
              聊天请求通过 JWT 用户网关，服务密钥只保留在后端。
            </p>
          </div>
          <a
            className="outline-button"
            href={apiBaseUrl + "/openapi.json"}
            target="_blank"
            rel="noreferrer"
          >
            <FileJson2 size={18} aria-hidden="true" />OpenAPI JSON
          </a>
        </section>
      </main>
    </div>
  );
}

function AuthPanel({
  mode,
  username,
  password,
  busy,
  message,
  onModeChange,
  onUsernameChange,
  onPasswordChange,
  onSubmit,
}: {
  mode: "login" | "register";
  username: string;
  password: string;
  busy: boolean;
  message: string;
  onModeChange: (mode: "login" | "register") => void;
  onUsernameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="auth-layout" aria-labelledby="auth-title">
      <div className="auth-copy">
        <p className="eyebrow">JWT 用户身份</p>
        <h2 id="auth-title">登录后开始和学习助手对话。</h2>
        <p>
          当前版本使用用户名和密码。登录成功后，浏览器只携带用户 JWT，
          Qwen 服务密钥不会进入浏览器。
        </p>
      </div>
      <form className="auth-form" onSubmit={onSubmit}>
        <div className="mode-switch" role="tablist" aria-label="账户操作">
          <button
            className={mode === "login" ? "mode-active" : ""}
            type="button"
            onClick={() => onModeChange("login")}
          >
            登录
          </button>
          <button
            className={mode === "register" ? "mode-active" : ""}
            type="button"
            onClick={() => onModeChange("register")}
          >
            注册
          </button>
        </div>
        <label>
          用户名
          <input
            value={username}
            onChange={(event) => onUsernameChange(event.target.value)}
            minLength={3}
            maxLength={50}
            autoComplete="username"
            required
          />
        </label>
        <label>
          密码
          <input
            type="password"
            value={password}
            onChange={(event) => onPasswordChange(event.target.value)}
            minLength={mode === "register" ? 8 : 1}
            maxLength={128}
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            required
          />
        </label>
        {message && (
          <p className="inline-error">
            <CircleAlert size={16} />{message}
          </p>
        )}
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "处理中..." : mode === "login" ? "进入工作区" : "创建并登录"}
          <LogIn size={17} />
        </button>
      </form>
    </section>
  );
}

function ChatPanel({
  draft,
  messages,
  streaming,
  retryText,
  chatError,
  onDraftChange,
  onSend,
  onCancel,
  onRetry,
}: {
  draft: string;
  messages: ViewMessage[];
  streaming: boolean;
  retryText: string | null;
  chatError: ErrorNotice | null;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
  onRetry: () => void;
}) {
  return (
    <section className="chat-panel" aria-labelledby="chat-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Qwen 用户网关</p>
          <h2 id="chat-title">学习助手</h2>
        </div>
        <span className="route-chip">POST /v1/user-chat/stream</span>
      </div>
      <div className="message-list" aria-live="polite">
        {messages.length === 0 && (
          <div className="empty-chat">
            <Bot size={28} />
            <strong>从一个问题开始</strong>
            <span>例如：请帮我把今天的学习目标拆成三个可执行步骤。</span>
          </div>
        )}
        {messages.map((message) => (
          <article
            className={
              "message message-" +
              message.role +
              (message.failed ? " message-failed" : "")
            }
            key={message.id}
          >
            <div className="message-avatar">
              {message.role === "user" ? <UserRound size={16} /> : <Bot size={16} />}
            </div>
            <div className="message-content">
              <span className="message-role">
                {message.role === "user" ? "你" : "学习助手"}
              </span>
              <p>{message.content || (message.pending ? "正在生成..." : "")}</p>
              {message.pending && (
                <span className="streaming-label">正在接收增量内容</span>
              )}
            </div>
          </article>
        ))}
      </div>

      {chatError && (
        <div className="chat-error" role="alert">
          <div className="chat-error-heading">
            <CircleAlert size={17} />
            <strong>{chatError.title}</strong>
            {chatError.status && <span>HTTP {chatError.status}</span>}
          </div>
          <p>{chatError.detail}</p>
          {chatError.code && <code>{chatError.code}</code>}
          {chatError.retryable && (
            <small>这是暂时性错误，可以稍后重新发送新的消息。</small>
          )}
        </div>
      )}

      {retryText && !streaming && (
        <button className="retry-button" type="button" onClick={onRetry}>
          重试上一条
        </button>
      )}

      <div className="composer">
        <textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="输入你想学习或拆解的问题..."
          rows={3}
          disabled={streaming}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
        />
        <div className="composer-foot">
          <span>Enter 发送，Shift + Enter 换行</span>
          {streaming ? (
            <button className="cancel-button" type="button" onClick={onCancel}>
              <X size={17} />取消生成
            </button>
          ) : (
            <button className="primary-button" type="button" onClick={onSend} disabled={!draft.trim()}>
              <Send size={17} />发送
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

function StatusCard({
  icon,
  title,
  state,
  tone,
}: {
  icon: ReactNode;
  title: string;
  state: CheckState;
  tone: "green" | "amber" | "blue";
}) {
  return (
    <article className={"status-card tone-" + tone}>
      <div className="status-icon" aria-hidden="true">{icon}</div>
      <div>
        <span className={"status-dot state-" + state.kind} />
        <p>{title}</p>
        <strong>{state.detail}</strong>
      </div>
    </article>
  );
}