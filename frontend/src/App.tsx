import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Database,
  FileJson2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { apiBaseUrl, getJson } from "./api/client";

type CheckState =
  | { kind: "checking"; detail: string }
  | { kind: "ready"; detail: string }
  | { kind: "failed"; detail: string };

type OverviewState = {
  api: CheckState;
  database: CheckState;
  contract: CheckState;
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
  if (!isRecord(value) || !isRecord(value[section])) {
    return false;
  }

  return value[section][key] === expected;
}

function errorDetail(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
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
    detail: `${Object.keys(body.paths).length} 条路径`,
  };
}

export default function App() {
  const [overview, setOverview] = useState<OverviewState>(checkingState);
  const [updatedAt, setUpdatedAt] = useState("-");
  const hasLoaded = useRef(false);

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
    if (hasLoaded.current) {
      return;
    }
    hasLoaded.current = true;
    void refresh();
  }, [refresh]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            知
          </span>
          <div>
            <strong>知行证据</strong>
            <span>AI 学习平台</span>
          </div>
        </div>

        <nav aria-label="预览导航">
          <div className="nav-current">
            <Activity size={18} aria-hidden="true" />
            <span>系统总览</span>
          </div>
        </nav>

        <div className="sidebar-foot">
          <ShieldCheck size={17} aria-hidden="true" />
          <span>Frontend-P1</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <span className="section-label">开发预览</span>
            <h1>服务总览</h1>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={() => void refresh()}
          >
            <RefreshCw size={18} aria-hidden="true" />
            <span className="sr-only">重新检查</span>
          </button>
        </header>

        <section className="summary" aria-labelledby="summary-title">
          <div>
            <p className="eyebrow">当前环境</p>
            <h2 id="summary-title">后端契约与运行状态</h2>
          </div>
          <div className="summary-meta">
            <span>API 基址</span>
            <code>{apiBaseUrl}</code>
            <small>更新于 {updatedAt}</small>
          </div>
        </section>

        <section className="status-grid" aria-label="服务检查结果">
          <StatusCard
            icon={<Activity size={21} />}
            title="应用接口"
            state={overview.api}
            tone="green"
          />
          <StatusCard
            icon={<Database size={21} />}
            title="数据连接"
            state={overview.database}
            tone="amber"
          />
          <StatusCard
            icon={<FileJson2 size={21} />}
            title="接口契约"
            state={overview.contract}
            tone="blue"
          />
        </section>

        <section className="contract-band" aria-labelledby="contract-title">
          <div>
            <p className="eyebrow">FastAPI</p>
            <h2 id="contract-title">接口契约</h2>
            <p className="supporting-copy">
              契约源：FastAPI OpenAPI
            </p>
          </div>
          <div className="contract-actions">
            <a
              href={`${apiBaseUrl}/openapi.json`}
              target="_blank"
              rel="noreferrer"
            >
              <FileJson2 size={18} aria-hidden="true" />
              OpenAPI JSON
            </a>
          </div>
        </section>
      </main>
    </div>
  );
}

function StatusCard({
  icon,
  title,
  state,
  tone,
}: {
  icon: React.ReactNode;
  title: string;
  state: CheckState;
  tone: "green" | "amber" | "blue";
}) {
  return (
    <article className={`status-card tone-${tone}`}>
      <div className="status-icon" aria-hidden="true">
        {icon}
      </div>
      <div>
        <span className={`status-dot state-${state.kind}`} />
        <p>{title}</p>
        <strong>{state.detail}</strong>
      </div>
    </article>
  );
}