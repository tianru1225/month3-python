import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  FileText,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Settings2,
  Sparkles,
  X,
} from "lucide-react";
import {
  ApiRequestError,
  clearStoredAccessToken,
  EvidenceAcceptance,
  getJson,
  getStoredAccessToken,
  postJson,
  Project,
  storeAccessToken,
  StreamEventError,
  Task,
  TodayTasks,
  uploadMaterial,
  User,
} from "./api/client";
import { exampleDecision, exampleTaskCatalog, exampleTasks, localDate, readExampleProgress } from "./learningTasks";
import type { EvidenceSubmission } from "./learningTasks";
import LearningChat from "./LearningChat";
import { createActivitySession, createTaskSession, readTaskArchive, taskDisplayId, taskKey } from "./taskSessions";
import type { SessionUpdate, TaskSource } from "./taskSessions";
import ReviewPage, { AdjustmentNotice } from "./ReviewPage";
import { activityGroup, knowledgeNodes, knowledgeState } from "./reviewLearning";
import type { LearningActivity } from "./reviewLearning";

type ViewKey = "overview" | "projects" | "progress";
type ProgressTab = "tasks" | "review";
type Notice = { tone: "success" | "error" | "info"; text: string };

const viewLabels: Record<ViewKey, string> = {
  overview: "今日学习",
  projects: "学习项目",
  progress: "学习进度",
};

const viewIcons: Record<ViewKey, ReactNode> = {
  overview: <LayoutDashboard size={18} />,
  projects: <FolderKanban size={18} />,
  progress: <ClipboardCheck size={18} />,
};

function navigationFromLocation(): { view: ViewKey; progressTab: ProgressTab } {
  const params = new URLSearchParams(window.location.search);
  const value = params.get("view");
  // 保留旧链接，让已有的任务与复习入口进入合并后的对应视图。
  if (value === "tasks" || value === "review") return { view: "progress", progressTab: value };
  return {
    view: value === "projects" || value === "progress" ? value : "overview",
    progressTab: params.get("tab") === "review" ? "review" : "tasks",
  };
}

function moveTo(path: string): void {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function errorText(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message;
  if (error instanceof StreamEventError) return error.message;
  return error instanceof Error ? error.message : "操作失败，请稍后重试";
}


function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    DRAFT: "草稿",
    READY: "待开始",
    IN_PROGRESS: "进行中",
    SUBMITTED: "待评价",
    EVALUATING: "评价中",
    PASSED: "已通过",
    REVISION_REQUIRED: "需要修订",
    READY_MATERIAL: "资料就绪",
    PENDING: "处理中",
    FAILED: "失败",
  };
  return labels[status] || status;
}

export default function App() {
  const [authReady, setAuthReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const stored = getStoredAccessToken();
    if (!stored) {
      setAuthReady(true);
      if (window.location.pathname !== "/login") window.history.replaceState({}, "", "/login");
      return;
    }
    setToken(stored);
    void getJson<User>("/users/me", stored)
      .then((profile) => setUser(profile))
      .catch(() => {
        clearStoredAccessToken();
        setToken(null);
        window.history.replaceState({}, "", "/login");
      })
      .finally(() => setAuthReady(true));
  }, []);

  useEffect(() => {
    if (authReady && token && user && window.location.pathname !== "/app") {
      window.history.replaceState({}, "", "/app?view=overview");
    }
  }, [authReady, token, user]);

  const login = (nextToken: string, profile: User) => {
    storeAccessToken(nextToken);
    setToken(nextToken);
    setUser(profile);
    moveTo("/app?view=overview");
  };

  const logout = () => {
    clearStoredAccessToken();
    setToken(null);
    setUser(null);
    window.history.replaceState({}, "", "/login");
  };

  if (!authReady) return <div className="loading-page">正在恢复登录状态…</div>;
  if (!token || !user) {
    return <LoginPage onLogin={login} alreadyAuthenticated={Boolean(token && user)} />;
  }
  return <Console key={user.id} user={user} token={token} onLogout={logout} />;
}

function LoginPage({
  onLogin,
  alreadyAuthenticated,
}: {
  onLogin: (token: string, user: User) => void;
  alreadyAuthenticated: boolean;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (alreadyAuthenticated) moveTo("/app?view=overview");
  }, [alreadyAuthenticated]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (mode === "register") await postJson<User>("/users", { username, password });
      const login = await postJson<{ access_token: string }>("/auth/login", { username, password });
      const profile = await getJson<User>("/users/me", login.access_token);
      onLogin(login.access_token, profile);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-visual">
        <div className="logo-mark">知</div>
        <p className="kicker">可验证的自适应学习平台</p>
        <h1>把学习目标，变成每天可以完成并验证的行动。</h1>
        <p className="login-lead">
          资料驱动计划，证据驱动评价。所有重要的学习进度都保留来源、状态和下一步。
        </p>
        <div className="login-points">
          <span><CheckCircle2 size={16} />资料先于计划</span>
          <span><CheckCircle2 size={16} />证据先于完成</span>
          <span><CheckCircle2 size={16} />用户确认重要变化</span>
        </div>
      </section>
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-card-head">
          <p className="kicker">学习工作台</p>
          <h2 id="login-title">{mode === "login" ? "欢迎回来" : "创建你的学习空间"}</h2>
          <p>{mode === "login" ? "登录后继续今天的学习任务。" : "注册后即可创建项目并上传第一份资料。"}</p>
        </div>
        <div className="segmented" role="tablist" aria-label="账户操作">
          <button className={mode === "login" ? "active" : ""} type="button" onClick={() => setMode("login")}>登录</button>
          <button className={mode === "register" ? "active" : ""} type="button" onClick={() => setMode("register")}>注册</button>
        </div>
        <form className="login-form" onSubmit={submit}>
          <label>用户名<input value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={50} autoComplete="username" required /></label>
          <label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={mode === "register" ? 8 : 1} maxLength={128} autoComplete={mode === "register" ? "new-password" : "current-password"} required /></label>
          {message && <p className="form-error"><CircleAlert size={16} />{message}</p>}
          <button className="primary-button wide" type="submit" disabled={busy}>{busy ? "处理中…" : mode === "login" ? "进入学习工作台" : "创建并登录"}<ArrowRight size={17} /></button>
        </form>
        <p className="login-security"><Settings2 size={14} />访问令牌只保留在当前浏览器会话中</p>
      </section>
    </main>
  );
}

function Console({ user, token, onLogout }: { user: User; token: string; onLogout: () => void }) {
  const [{ view, progressTab }, setNavigation] = useState(navigationFromLocation);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [bindings, setBindings] = useState<import("./api/client").MaterialBinding[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const planStorageKey = `learning.plan-versions.${user.id}`;
  const [planVersions, setPlanVersions] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem(planStorageKey) || "{}"); }
    catch { return {}; }
  });
  const planVersionId = projectId ? planVersions[projectId] || "" : "";
  const [targetDate, setTargetDate] = useState(localDate);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(false);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [materialProject, setMaterialProject] = useState<Project | null>(null);

  const selectedProject = useMemo(() => projects.find((item) => item.id === projectId) || null, [projects, projectId]);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getJson<Project[]>("/projects", token);
      setProjects(result);
      setProjectId((current) => current && result.some((item) => item.id === current) ? current : result[0]?.id || null);
    } catch (error) {
      setNotice({ tone: "error", text: errorText(error) });
    } finally {
      setLoading(false);
    }
  }, [token]);

  const loadBindings = useCallback(async () => {
    if (!projectId) { setBindings([]); return; }
    try {
      setBindings(await getJson<import("./api/client").MaterialBinding[]>(`/projects/${projectId}/materials`, token));
    } catch (error) {
      setNotice({ tone: "error", text: errorText(error) });
    }
  }, [projectId, token]);

  const [taskLoading, setTaskLoading] = useState(false);
  const [taskError, setTaskError] = useState("");
  const [taskRefresh, setTaskRefresh] = useState(0);
  const loadTasks = () => setTaskRefresh((value) => value + 1);

  useEffect(() => {
    const updateDate = () => setTargetDate(localDate());
    const timer = window.setInterval(updateDate, 30_000);
    window.addEventListener("focus", updateDate);
    document.addEventListener("visibilitychange", updateDate);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", updateDate); document.removeEventListener("visibilitychange", updateDate); };
  }, []);

  useEffect(() => {
    let active = true;
    setTasks([]);
    setSelectedTask(null);
    setTaskError("");
    if (!projectId || !planVersionId) { setTaskLoading(false); return; }
    setTaskLoading(true);
    void getJson<TodayTasks>(`/projects/${projectId}/plan-versions/${planVersionId}/today-tasks?target_date=${targetDate}`, token)
      .then((response) => { if (active) setTasks(response.tasks); })
      .catch((error) => { if (active) setTaskError(errorText(error)); })
      .finally(() => { if (active) setTaskLoading(false); });
    return () => { active = false; };
  }, [projectId, planVersionId, targetDate, token, taskRefresh]);

  const setPlanVersionId = (value: string) => {
    if (!projectId) return;
    const next = { ...planVersions, [projectId]: value.trim() };
    setPlanVersions(next);
    try { localStorage.setItem(planStorageKey, JSON.stringify(next)); }
    catch { setNotice({ tone: "error", text: "浏览器无法保存计划设置，刷新后需要重新选择。" }); }
    loadTasks();
  };

  useEffect(() => { void loadProjects(); }, [loadProjects]);
  useEffect(() => { void loadBindings(); }, [loadBindings]);
  useEffect(() => {
    const onPopState = () => setNavigation(navigationFromLocation());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (next: ViewKey, tab: ProgressTab = "tasks") => {
    setSidebarOpen(false);
    moveTo(`/app?view=${next}${next === "progress" ? `&tab=${tab}` : ""}`);
    window.scrollTo(0, 0);
  };

  const openMaterialModal = (project: Project) => {
    setProjectId(project.id);
    setMaterialProject(project);
  };

  const refresh = async () => {
    await loadProjects();
    await loadBindings();
    loadTasks();
  };


  return (
    <div className="console-shell">
      {sidebarOpen && <button className="mobile-backdrop" aria-label="关闭导航" onClick={() => setSidebarOpen(false)} />}
      <aside className={`console-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="console-brand"><div className="brand-mark">知</div><div><strong>知行</strong><span>AI 学习工作台</span></div></div>
        <div className="sidebar-caption">学习空间</div>
        <nav className="console-nav" aria-label="主导航">
          {(Object.keys(viewLabels) as ViewKey[]).map((item) => <button key={item} className={view === item ? "selected" : ""} aria-current={view === item ? "page" : undefined} type="button" onClick={() => navigate(item)}>{viewIcons[item]}<span>{viewLabels[item]}</span></button>)}
        </nav>
        <div className="sidebar-footer"><div className="user-chip"><span>{user.username.slice(0, 1).toUpperCase()}</span><div><strong>{user.username}</strong><small>学习者</small></div></div><button className="sidebar-icon" type="button" title="退出登录" onClick={onLogout}><LogOut size={17} /></button></div>
      </aside>
      <main className="console-main">
        <header className="console-topbar"><button className="mobile-menu" type="button" onClick={() => setSidebarOpen(true)}><Menu size={20} /></button><div><p className="kicker">{viewLabels[view]}</p><h1>{selectedProject ? selectedProject.name : "你的学习工作台"}</h1></div><div className="topbar-actions"><select aria-label="选择学习项目" value={projectId || ""} onChange={(event) => setProjectId(event.target.value ? Number(event.target.value) : null)}><option value="">选择项目</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select><button className="icon-button" type="button" onClick={() => void refresh()} title="刷新"><RefreshCw size={18} /></button><button className="text-button logout-desktop" type="button" onClick={onLogout}><LogOut size={16} />退出</button></div></header>
        {notice && <div className={`notice ${notice.tone}`} role="status">{notice.tone === "error" ? <CircleAlert size={17} /> : <CheckCircle2 size={17} />}<span>{notice.text}</span><button type="button" onClick={() => setNotice(null)}><X size={15} /></button></div>}
        <div className="page-content">
          <div hidden={view === "projects"}><LearningWorkspace key={`${user.id}:${projectId}`} view={view} progressTab={progressTab} onNavigate={navigate} token={token} scope={`${user.id}.${projectId ?? "preview"}`} projectId={projectId} today={targetDate} planVersionId={planVersionId} onPlanVersionChange={setPlanVersionId} tasks={tasks} loading={loading || taskLoading} error={taskError} onEvidence={setSelectedTask} /></div>
          {view === "projects" && <ProjectsPage projects={projects} onCreateRequest={() => setCreateProjectOpen(true)} onOpenMaterial={openMaterialModal} />}
        </div>
      </main>
      {createProjectOpen && <ProjectNameModal token={token} onClose={() => setCreateProjectOpen(false)} onCreated={async (project) => { setCreateProjectOpen(false); await loadProjects(); setProjectId(project.id); setMaterialProject(project); setNotice({ tone: "success", text: "项目已创建，请添加第一份资料" }); }} />}
      {materialProject && <ProjectMaterialModal token={token} project={materialProject} bindings={bindings} onClose={() => setMaterialProject(null)} onUploaded={async () => { await loadBindings(); setNotice({ tone: "success", text: "资料已上传并绑定，正在解析" }); }} />}
      {selectedTask && <EvidenceModal task={selectedTask} token={token} onClose={() => setSelectedTask(null)} onResult={(status) => { setTasks((items) => items.map((item) => item.id === selectedTask.id ? { ...item, status } : item)); }} />}
    </div>
  );
}

function ProjectNameModal({ token, onClose, onCreated }: { token: string; onClose: () => void; onCreated: (project: Project) => Promise<void> }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEscapeToClose(onClose);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) { setMessage("请输入项目名称"); return; }
    setBusy(true);
    setMessage("");
    try {
      const project = await postJson<Project>("/projects", { name: name.trim() }, token);
      await onCreated(project);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return <SimpleModal title="新建学习项目" description="先给这段学习旅程起个名字。" onClose={onClose}><form className="simple-project-form" onSubmit={submit}><label>项目名称<input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：Python 基础" /></label>{message && <p className="form-error"><CircleAlert size={16} />{message}</p>}<button className="primary-button wide rounded-action" type="submit" disabled={busy}>{busy ? "创建中…" : "创建项目"}<ArrowRight size={16} /></button></form></SimpleModal>;
}

function ProjectMaterialModal({ token, project, bindings, onClose, onUploaded }: { token: string; project: Project; bindings: import("./api/client").MaterialBinding[]; onClose: () => void; onUploaded: () => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEscapeToClose(onClose);
  const chooseFile = (next: File | null) => { if (next) setFile(next); };
  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await uploadMaterial(token, file.name, file, "");
      await postJson(`/projects/${project.id}/materials/${result.material_id}`, {}, token);
      await postJson(`/materials/${result.material_id}/versions/${result.version_id}/parse`, {}, token);
      setMessage("资料已添加，正在解析");
      setFile(null);
      const input = document.getElementById("project-material-file") as HTMLInputElement | null;
      if (input) input.value = "";
      await onUploaded();
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return <SimpleModal title={`为「${project.name}」添加资料`} description="上传一份 Markdown 文档，从第一节开始学习。" onClose={onClose}><div className={`material-drop-zone ${dragging ? "is-dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0] || null); }}><input id="project-material-file" type="file" accept=".md,.markdown,text/markdown,text/plain" onChange={(event) => chooseFile(event.target.files?.[0] || null)} /><label className="material-add-button" htmlFor="project-material-file" aria-label="选择资料"><Plus size={22} /></label><strong>{file ? file.name : "拖入 Markdown 文件"}</strong><span>{file ? `${Math.ceil(file.size / 1024)} KB · 已选择` : "或点击加号从本机选择"}</span></div>{file && <button className="selected-file" type="button" onClick={() => setFile(null)}><FileText size={16} /><span>{file.name}</span><X size={15} /></button>}{bindings.length > 0 && <p className="material-count">当前项目已有 {bindings.length} 份资料</p>}{message && <p className="upload-message">{message}</p>}<button className="primary-button wide rounded-action" type="button" disabled={!file || busy} onClick={() => void submit()}>{busy ? "添加中…" : "添加资料"}<Plus size={16} /></button></SimpleModal>;
}

function useEscapeToClose(onClose: () => void) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
}

function SimpleModal({ title, description, onClose, children }: { title: string; description?: string; onClose: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (!dialog.current?.contains(document.activeElement)) dialog.current?.focus();
    return () => { document.body.style.overflow = previousOverflow; previousFocus?.focus(); };
  }, []);
  return <div className="simple-modal-backdrop" role="presentation" onMouseDown={onClose}><section ref={dialog} tabIndex={-1} className="simple-modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()} onKeyDown={(event) => {
    if (event.key !== "Tab") return;
    const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled)')].filter((item) => !item.closest("fieldset:disabled"));
    const first = controls[0]; const last = controls[controls.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { event.preventDefault(); first?.focus(); }
  }}><button className="simple-modal-close" type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button><p className="kicker">学习工作台</p><h2>{title}</h2>{description && <p className="simple-modal-description">{description}</p>}{children}</section></div>;
}

function LearningWorkspace({ token, view, progressTab, onNavigate, scope, projectId, today, planVersionId, onPlanVersionChange, tasks, loading, error, onEvidence }: {
  token: string; view: ViewKey; progressTab: ProgressTab; onNavigate: (view: ViewKey, tab?: ProgressTab) => void; scope: string; projectId: number | null;
  today: string; planVersionId: string; onPlanVersionChange: (value: string) => void;
  tasks: Task[]; loading: boolean; error: string; onEvidence: (task: Task) => void;
}) {
  const storageKey = `learning.python-examples.${scope}`;
  const archiveKey = `learning.task-conversations.v1.${scope}`;
  const realMode = Boolean(planVersionId);
  const [initialProgress] = useState(() => readExampleProgress(storageKey, today));
  const [storageError, setStorageError] = useState(initialProgress.error);
  const [progress, setProgress] = useState(initialProgress.progress);
  const [initialArchive] = useState(() => readTaskArchive(archiveKey));
  const [archive, setArchive] = useState(() => ({ ...initialArchive.archive, reviewStartedOn: initialArchive.archive.reviewStartedOn || today }));
  const [archiveError, setArchiveError] = useState(initialArchive.error);
  const [mobilePane, setMobilePane] = useState<"tasks" | "chat">(initialArchive.archive.selectedId ? "chat" : "tasks");
  const [query, setQuery] = useState("");
  const [planDraft, setPlanDraft] = useState(planVersionId);
  const [exampleTask, setExampleTask] = useState<Task | null>(null);
  const [proposalOpen, setProposalOpen] = useState(false);
  useEffect(() => setPlanDraft(planVersionId), [planVersionId]);
  useEffect(() => {
    if (initialArchive.error) return;
    try { localStorage.setItem(archiveKey, JSON.stringify(archive)); setArchiveError(""); }
    catch { setArchiveError("浏览器无法保存对话；当前修改仅在本页暂存，刷新前请复制需要的内容。"); }
  }, [archive, archiveKey, initialArchive.error]);
  useEffect(() => {
    if (realMode || initialProgress.error) return;
    try { localStorage.setItem(storageKey, JSON.stringify(progress)); setStorageError(""); }
    catch { setStorageError("浏览器无法保存示例进度，请允许网站存储后再提交。"); }
  }, [storageKey, progress, realMode, initialProgress.error]);
  const visibleTasks = realMode ? tasks : exampleTasks(progress, today);
  const pending = visibleTasks.filter((task) => task.status !== "PASSED");
  const completed = visibleTasks.filter((task) => task.status === "PASSED");
  const examples = useMemo(() => exampleTaskCatalog(progress), [progress]);
  // 保存任务快照，以便任务离开今日列表后仍可检索。快照不作为真实提交状态的依据。
  useEffect(() => {
    setArchive((current) => {
      let changed = false;
      const sessions = current.sessions.map((session) => {
        const fresh = session.source === "example" ? !initialProgress.error && examples.find((task) => task.id === session.task.id)
          : tasks.find((task) => taskKey(task, "real") === session.taskKey);
        if (!fresh || JSON.stringify(fresh) === JSON.stringify(session.task)) return session;
        changed = true;
        return { ...session, task: fresh };
      });
      return changed ? { ...current, sessions } : current;
    });
  }, [examples, tasks, initialProgress.error]);
  const updateSession = useCallback((id: string, patch: SessionUpdate) => {
    setArchive((current) => {
      const session = current.sessions.find((item) => item.id === id);
      if (!session || (session.mode === patch.mode && session.step === patch.step && session.draft === patch.draft && JSON.stringify(session.messages) === JSON.stringify(patch.messages) && JSON.stringify(session.activity) === JSON.stringify(patch.activity))) return current;
      return { ...current, sessions: current.sessions.map((item) => item.id === id ? { ...item, ...patch, updatedAt: new Date().toISOString() } : item) };
    });
  }, []);
  const selectSession = (id: string) => {
    setArchive((current) => ({ ...current, selectedId: id }));
    setMobilePane("chat");
    onNavigate("overview");
  };
  const openTask = (task: Task, source: TaskSource, restart = false) => {
    setArchive((current) => {
      const previous = current.sessions.find((item) => item.taskKey === taskKey(task, source) && !item.activity);
      if (previous && !restart) return { ...current, selectedId: previous.id };
      const session = createTaskSession(task, source);
      return { ...current, selectedId: session.id, sessions: [session, ...current.sessions] };
    });
    setMobilePane("chat");
    onNavigate("overview");
  };
  const openActivity = (nodeId: number, kind: LearningActivity["kind"], restart = false) => {
    const node = knowledgeNodes.find((item) => item.id === nodeId);
    const task = examples.find((item) => item.id === node?.taskId);
    if (!task) return;
    setArchive((current) => {
      const records = current.sessions.filter((item) => item.activity?.nodeId === nodeId && item.activity.kind === kind);
      const latest = records[0];
      if (latest && !latest.activity?.completedAt && !restart) return { ...current, selectedId: latest.id };
      const exposed = records.some((item) => (item.activity?.hinted || item.activity?.completedAt) && localDate(new Date(item.activity?.completedAt || item.updatedAt)) === today);
      const session = createActivitySession(task, { kind, nodeId, hinted: exposed, priorExposure: exposed });
      return { ...current, selectedId: session.id, sessions: [session, ...current.sessions] };
    });
    setMobilePane("chat");
    onNavigate("overview");
  };
  const openOriginal = (id: number) => { const task = examples.find((item) => item.id === id); if (task) openTask(task, "example"); };
  const selected = archive.sessions.find((item) => item.id === archive.selectedId);
  const siblings = selected ? archive.sessions.filter((item) => activityGroup(item) === activityGroup(selected)) : [];
  const readOnly = Boolean(selected && siblings[0]?.id !== selected.id);
  const currentTask = selected && (selected.source === "example" ? !initialProgress.error && examples.find((task) => task.id === selected.task.id)
    : tasks.find((task) => taskKey(task, "real") === selected.taskKey)) || selected?.task;
  const canSubmit = Boolean(selected && !selected.activity && !readOnly && (selected.source === "example"
    ? !initialProgress.error && currentTask?.scheduled_date && currentTask.scheduled_date <= today
    : !loading && !error && tasks.some((task) => taskKey(task, "real") === selected.taskKey && String(task.plan_version_id) === planVersionId)));
  const source: TaskSource = realMode ? "real" : "example";
  const nextTask = selected?.source === source ? pending.find((task) => taskKey(task, source) !== selected.taskKey) : undefined;
  const dueReviews = knowledgeNodes.filter((node) => knowledgeState(node, archive, today).isDue);
  const reinforcement = archive.sessions.find((item) => item.activity?.kind === "reinforcement");
  const reinforcementPassed = Boolean(reinforcement?.activity?.completedAt && reinforcement.activity.outcome !== "retry");
  const adjustmentActive = !realMode && archive.adjustment?.status === "accepted";
  const recommended = adjustmentActive ? [...pending.filter((task) => task.id === 3), ...pending.filter((task) => task.id !== 3)] : pending;
  const recommendationLimit = adjustmentActive && !reinforcementPassed ? 2 : 3;
  const catalog = new Map<string, { task: Task; source: TaskSource }>();
  // 最新一轮快照优先；今日接口与示例进度再覆盖快照。
  [...archive.sessions].reverse().forEach((session) => catalog.set(session.taskKey, { task: session.task, source: session.source }));
  (realMode ? tasks : examples).forEach((task) => { if (realMode || !initialProgress.error || !catalog.has(taskKey(task, source))) catalog.set(taskKey(task, source), { task, source }); });
  const search = query.trim().toLowerCase();
  const history = [...catalog.values()].filter(({ task, source: itemSource }) => !search || `${task.title} ${taskDisplayId(task, itemSource)} ${task.id}`.toLowerCase().includes(search));
  const saveExample = async (task: Task, evidence: EvidenceSubmission) => {
    if (initialProgress.error) throw new Error(initialProgress.error);
    const status = exampleDecision(evidence);
    const next = { ...progress, results: { ...progress.results, [task.id]: { status, evidence, completedAt: status === "PASSED" ? `${today}T${new Date().toTimeString().slice(0, 8)}` : null } } };
    // 先保存再更新界面，存储失败时不显示虚假的提交成功。
    localStorage.setItem(storageKey, JSON.stringify(next));
    setProgress(next);
    return status;
  };
  return (
    <>
    {archiveError && <p className="form-error storage-warning" role="alert">{archiveError}</p>}
    <div hidden={view !== "overview"}>
    <div className="learning-mobile-tabs" aria-label="学习区域"><button type="button" className={mobilePane === "tasks" ? "active" : ""} onClick={() => setMobilePane("tasks")}>今日任务 · {pending.length}</button><button type="button" className={mobilePane === "chat" ? "active" : ""} onClick={() => setMobilePane("chat")}>学习对话{selected ? ` · ${taskDisplayId(selected.task, selected.source)}` : ""}</button></div>
    <div className={`today-learning-layout mobile-${mobilePane}`}>
      <LearningChat key={selected?.id || "free"} token={token} active={view === "overview"} session={selected} task={currentTask} readOnly={readOnly} sessions={siblings} onSessionUpdate={updateSession} onSelectSession={selectSession}
        onRestart={() => { if (selected?.activity) openActivity(selected.activity.nodeId, selected.activity.kind, true); else if (selected && currentTask) openTask(currentTask, selected.source, true); }}
        onLeave={() => setArchive((current) => ({ ...current, selectedId: null }))}
        onOriginal={selected?.activity ? () => openOriginal(selected.task.id) : undefined}
        onReviewPage={() => onNavigate("progress", "review")}
        onSubmit={canSubmit && selected && currentTask ? () => selected.source === "example" ? setExampleTask(currentTask) : onEvidence(currentTask) : undefined}
        onNextTask={nextTask ? () => openTask(nextTask, source) : undefined}
        onStartTask={pending[0] && !loading && !error ? () => adjustmentActive && !reinforcementPassed ? openActivity(3, "reinforcement") : openTask(recommended[0], source) : undefined}
        storageWarning={Boolean(archiveError)} layoutPane={mobilePane} />
      <aside className="surface-card today-workbench" aria-labelledby="today-workbench-title">
        <div className="card-heading">
          <div><p className="kicker">今日工作台</p><h3 id="today-workbench-title">先完成最重要的一步</h3></div>
        </div>
        <p className="workbench-caption">{today} · {pending.length} 项待完成</p>
        <p className="workbench-caption">点击任务，左侧开始分步学习；再次点击继续原对话。</p>
        {realMode && <p className="workbench-caption">真实接口仅加载当天任务，历史未完成任务尚不自动顺延。</p>}
        {!realMode && <p className="example-note">Python 示例任务 · 进度保存在此浏览器，不计入真实项目</p>}
        {storageError && !realMode && <p className="form-error" role="alert">{storageError}</p>}
        {!realMode && dueReviews[0] && <button className={`workbench-activity ${selected?.activity?.kind === "review" && selected.activity.nodeId === dueReviews[0].id ? "is-selected" : ""}`} type="button" onClick={() => openActivity(dueReviews[0].id, "review")}><span className="review-eyebrow">温习一点 · 固定题演示</span><strong>{dueReviews[0].title}<RefreshCw size={15} /></strong><small>约 3 分钟 · 全部建议可在学习进度中查看</small></button>}
        {adjustmentActive && !reinforcementPassed && <button className={`workbench-activity reinforcement ${selected?.activity?.kind === "reinforcement" ? "is-selected" : ""}`} type="button" onClick={() => openActivity(3, "reinforcement")}><span className="review-eyebrow">已采用的调整 · 补基础演示</span><strong>分清 print 与 return<ArrowRight size={15} /></strong><small>约 3 分钟 · 接着回到 PY-003</small></button>}
        {adjustmentActive && reinforcementPassed && <p className="workbench-caption">补基础练习已答对，可继续原函数任务。原任务仍需单独提交成果。</p>}
        {loading ? <p role="status">正在加载今日任务…</p> : realMode && error ? <p className="form-error" role="alert">任务加载失败：{error}，请使用顶部刷新重试。</p> : <>
          {pending.length ? <><p className="workbench-caption">接下来推荐 · 其余任务继续保留</p><div className="task-preview-list">{recommended.slice(0, recommendationLimit).map((task) => <TaskRow key={task.id} task={task} source={source} selected={!selected?.activity && selected?.taskKey === taskKey(task, source)} today={today} onClick={() => openTask(task, source)} />)}</div>{recommended.length > recommendationLimit && <details className="completed-tasks remaining-tasks"><summary>其余待学 · {recommended.length - recommendationLimit}</summary>{recommended.slice(recommendationLimit).map((task) => <TaskRow key={task.id} task={task} source={source} selected={!selected?.activity && selected?.taskKey === taskKey(task, source)} today={today} onClick={() => openTask(task, source)} />)}</details>}</> : <EmptyState icon={<CheckCircle2 size={22} />} title={completed.length ? "今天的任务已完成" : "今天暂无待办"} text="按自己的节奏继续学习，也可以在学习进度中回顾已有记录。" />}
          {completed.length > 0 && <details className="completed-tasks"><summary>今日已完成 · {completed.length}</summary>{completed.map((task) => <TaskRow key={task.id} task={task} source={source} selected={!selected?.activity && selected?.taskKey === taskKey(task, source)} today={today} onClick={() => openTask(task, source)} />)}</details>}
        </>}
        <button className="workbench-history-link" type="button" onClick={() => onNavigate("progress")}>查看学习进度与记录<ArrowRight size={15} /></button>
      </aside>
    </div>
    </div>
    {view === "progress" && <div className="learning-progress">
      <section className="page-intro"><div><p className="kicker">学习进度</p><h2>学到哪里，记住多少</h2><p>找回任务与对话，也看看学过的知识是否还会。继续学习和复习，都回到今日学习。</p></div></section>
      <div className="progress-toolbar">
        <div className="progress-switcher" role="group" aria-label="学习进度视图">
          <button type="button" aria-pressed={progressTab === "tasks"} aria-controls="progress-content" onClick={() => onNavigate("progress", "tasks")}><ClipboardCheck size={16} />任务与记录</button>
          <button type="button" aria-pressed={progressTab === "review"} aria-controls="progress-content" onClick={() => onNavigate("progress", "review")}><RefreshCw size={16} />知识与复习<span className="progress-demo-label">演示</span></button>
        </div>
        <span className="progress-storage-note">对话与复习记录仅保存在本机</span>
      </div>
      <details className="plan-connection"><summary>{realMode ? `已连接计划 #${planVersionId}` : "当前体验 Python 示例"} · 连接真实计划</summary><form className="task-query" onSubmit={(event) => { event.preventDefault(); setArchive((current) => ({ ...current, selectedId: null })); onPlanVersionChange(planDraft); }}><label>已发布计划 ID<input type="number" min="1" step="1" value={planDraft} onChange={(event) => setPlanDraft(event.target.value)} placeholder="填写真实计划 ID；留空使用示例" /></label><button className="primary-button" type="submit" disabled={!projectId || loading}>{planDraft ? "连接计划" : "使用 Python 示例"}</button></form><p className="workbench-caption">真实任务仅包含接口已加载和本机有学习记录的任务，尚未同步服务端历史。</p></details>
      {!realMode && <AdjustmentNotice archive={archive} onPreview={() => setProposalOpen(true)} />}
      {error && <p className="form-error" role="alert">计划任务加载失败：{error}</p>}
      {loading && <p role="status">正在加载任务…</p>}
      <div id="progress-content" role="region" aria-label={progressTab === "tasks" ? "任务与记录" : "知识与复习"}>
      {progressTab === "tasks" ? <>
      <div className="task-history-tools"><label>查找任务<input type="search" placeholder="搜索任务名称或 ID，如 PY-001" value={query} onChange={(event) => setQuery(event.target.value)} /></label><span>当前可见 {history.length} 项任务 · 本项目共 {archive.sessions.length} 轮记录</span></div>
      <section className="task-history-list" aria-label="任务与学习记录">{history.map(({ task, source: itemSource }) => {
        const records = archive.sessions.filter((item) => item.taskKey === taskKey(task, itemSource));
        const node = itemSource === "example" ? knowledgeNodes.find((item) => item.taskId === task.id) : undefined;
        const knowledge = node ? knowledgeState(node, archive, today) : undefined;
        return <article className="surface-card task-history-card" key={taskKey(task, itemSource)}>
          <div className="task-history-info"><div className="task-history-meta"><span>{taskDisplayId(task, itemSource)}</span><span>{itemSource === "example" ? "Python 示例" : `真实计划 #${task.plan_version_id}`}</span><span className={`status-pill status-${task.status.toLowerCase()}`}>{statusLabel(task.status)}</span></div><h3>{task.title}</h3><p>{task.objective}</p><small>{records.length ? `最近学习 ${new Date(records[0].updatedAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })} · ${records.length} 轮记录` : `尚未开始对话 · 计划日期 ${task.scheduled_date || "未安排"}`}</small></div>
          <button className="secondary-button" type="button" onClick={() => openTask(task, itemSource)}>{records.length ? task.status === "PASSED" ? "查看记录" : "继续学习" : "开始学习"}<ArrowRight size={15} /></button>
          {node && knowledge && <div className="task-knowledge-summary"><div><span className="task-knowledge-label">{knowledge.seeded ? "预置演示" : "本机固定题"}</span><span>知识表现 · {knowledge.level}</span><span className={knowledge.isDue ? "task-review-due" : ""}>{knowledge.isDue ? "复习 · 今天建议" : knowledge.due ? `下次复习 · ${knowledge.due}` : "复习 · 尚未安排"}</span></div><button className="link-button" type="button" onClick={() => openActivity(node.id, "review")}>{knowledge.isDue ? "去复习" : "练一题"}<ArrowRight size={14} /></button></div>}
          {records.length > 0 && <details className="task-session-history"><summary>学习与复习记录 · {records.length}</summary>{records.map((record) => { const group = records.filter((item) => activityGroup(item) === activityGroup(record)); const index = group.findIndex((item) => item.id === record.id); return <button key={record.id} type="button" onClick={() => selectSession(record.id)}><span>{record.activity ? record.activity.kind === "review" ? "复习" : "补基础" : "学习"} · 第 {group.length - index} 轮 · {record.activity?.completedAt ? "已核对" : index === 0 ? "当前对话" : "历史记录"}</span><span>{new Date(record.startedAt).toLocaleString("zh-CN")} · {record.messages.length} 条消息<ArrowRight size={14} /></span></button>; })}</details>}
        </article>;
      })}</section>
      {!history.length && <EmptyState icon={<ClipboardCheck size={22} />} title={query ? "没有找到匹配的任务" : "还没有任务记录"} text={query ? "试试任务名称、数字编号或 PY-001。" : "选择示例或连接已发布计划后开始学习。"} />}
      </> : <ReviewPage archive={archive} today={today} realMode={realMode} onReview={(id) => openActivity(id, "review")} onOriginal={openOriginal} onSession={selectSession} />}
      </div>
    </div>}
    {proposalOpen && <AdjustmentModal accepted={archive.adjustment?.status === "accepted"} realMode={realMode} onClose={() => setProposalOpen(false)} onDecide={(status) => { setArchive((current) => ({ ...current, adjustment: { status, decidedAt: new Date().toISOString() } })); setProposalOpen(false); if (status === "accepted" && !realMode) { setMobilePane("tasks"); onNavigate("overview"); } }} />}
    {exampleTask && <EvidenceModal key={exampleTask.id} task={exampleTask} savedEvidence={progress.results[exampleTask.id]?.evidence} onClose={() => setExampleTask(null)} onExampleSubmit={(evidence) => saveExample(exampleTask, evidence)} />}
    </>
  );
}
function ProjectsPage({ projects, onCreateRequest, onOpenMaterial }: { projects: Project[]; onCreateRequest: () => void; onOpenMaterial: (project: Project) => void }) {
  return <><section className="page-intro"><div><p className="kicker">项目空间</p><h2>从一份资料开始，完成一段学习</h2><p>每个项目都是一个学习空间。先命名，再上传你要从头学起的 Markdown 资料。</p></div><button className="primary-button" type="button" onClick={onCreateRequest}><Plus size={17} />新建项目</button></section><div className="project-grid">{projects.length ? projects.map((project) => <button className="project-card project-card-button" key={project.id} type="button" onClick={() => onOpenMaterial(project)}><div className="project-card-top"><span className="status-pill status-ready">{statusLabel(project.status)}</span><span className="project-id">#{project.id}</span></div><h3>{project.name}</h3><p>点击添加或继续添加学习资料</p><dl><div><dt>资料入口</dt><dd>添加 Markdown</dd></div><div><dt>项目状态</dt><dd>{statusLabel(project.status)}</dd></div></dl></button>) : <EmptyState icon={<FolderKanban size={22} />} title="还没有学习项目" text="创建第一个项目，随后上传第一份资料。" action="新建项目" onClick={onCreateRequest} />}</div></>;
}

function EvidenceModal({ task, token, savedEvidence, onClose, onExampleSubmit, onResult }: { task: Task; token?: string; savedEvidence?: EvidenceSubmission; onClose: () => void; onExampleSubmit?: (evidence: EvidenceSubmission) => Promise<string>; onResult?: (status: string) => void }) {
  const [mode, setMode] = useState<"TEXT_ANSWER" | "TEST_REPORT">(savedEvidence?.evidence_type || "TEXT_ANSWER");
  const [text, setText] = useState(savedEvidence?.evidence_type === "TEXT_ANSWER" ? savedEvidence.text_content : "");
  const report = savedEvidence?.evidence_type === "TEST_REPORT" ? savedEvidence.test_report : null;
  const [command, setCommand] = useState(report?.command || "pytest -q");
  const [summary, setSummary] = useState(report?.summary || "");
  const [exitCode, setExitCode] = useState(String(report?.exit_code ?? 0));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState(task.status);
  const [submitted, setSubmitted] = useState(task.status === "SUBMITTED");
  const close = () => { if (!busy) onClose(); };
  useEscapeToClose(close);
  const canSubmit = status === "IN_PROGRESS" || (Boolean(onExampleSubmit) && status === "REVISION_REQUIRED") || submitted;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !canSubmit) return;
    const payload: EvidenceSubmission = mode === "TEXT_ANSWER"
      ? { evidence_type: "TEXT_ANSWER", text_content: text.trim() }
      : { evidence_type: "TEST_REPORT", test_report: { command: command.trim(), exit_code: Number(exitCode), summary: summary.trim(), checks: [{ name: "用户提交的检查", status: Number(exitCode) === 0 ? "PASSED" : "FAILED", details: summary.trim() }] } };
    if (!submitted && (mode === "TEXT_ANSWER" ? !text.trim() : !command.trim() || !summary.trim())) { setMessage("请填写完整的证据内容。"); return; }
    setBusy(true);
    setMessage("");
    try {
      let nextStatus: string;
      if (onExampleSubmit) nextStatus = await onExampleSubmit(payload);
      else {
        const path = `/plan-versions/${task.plan_version_id}/tasks/${task.id}`;
        if (!submitted) {
          await postJson(`${path}/evidence`, payload, token);
          setSubmitted(true);
          setStatus("SUBMITTED");
          onResult?.("SUBMITTED");
        }
        const result = await postJson<EvidenceAcceptance>(`${path}/evaluate`, {}, token);
        nextStatus = result.task_status;
      }
      setStatus(nextStatus);
      setSubmitted(false);
      onResult?.(nextStatus);
    } catch (error) { setMessage(errorText(error)); }
    finally { setBusy(false); }
  };
  return <SimpleModal title={task.title} description={task.objective} onClose={close}>
    <div className="evidence-task-summary"><span className={`status-pill status-${status.toLowerCase()}`} role="status">{statusLabel(status)}</span><p>交付内容：{task.deliverable}</p><ul>{task.acceptance_criteria.map((item, index) => <li key={index}>{item}</li>)}</ul></div>
    {onExampleSubmit && <p className="example-note">示例规则：非空文本通过；测试报告须退出码为 0。此处不执行命令，也不评判答案内容的正确性。</p>}
    {status === "PASSED" ? <p className="evidence-success" role="status"><CheckCircle2 size={18} />任务已通过，继续下一步吧。</p> : <form className="evidence-form" onSubmit={submit}>
      {!submitted && canSubmit && <>
        <div className="segmented evidence-switch"><button className={mode === "TEXT_ANSWER" ? "active" : ""} type="button" disabled={busy} onClick={() => setMode("TEXT_ANSWER")}>文本答案</button><button className={mode === "TEST_REPORT" ? "active" : ""} type="button" disabled={busy} onClick={() => setMode("TEST_REPORT")}>测试报告</button></div>
        <fieldset className="evidence-fields" disabled={busy}>{mode === "TEXT_ANSWER" ? <label>答案内容<textarea autoFocus rows={7} value={text} onChange={(event) => setText(event.target.value)} placeholder="写出你的理解、过程和关键结果…" required /></label> : <div className="form-grid"><label>执行命令<input value={command} onChange={(event) => setCommand(event.target.value)} required /></label><label>退出码<input type="number" min="0" max="255" step="1" value={exitCode} onChange={(event) => setExitCode(event.target.value)} required /></label><label className="span-2">测试摘要<textarea rows={5} value={summary} onChange={(event) => setSummary(event.target.value)} required /></label></div>}</fieldset>
      </>}
      {submitted && <p role="status">证据已保存，继续评价即可，无需重复提交。</p>}
      {status === "REVISION_REQUIRED" && <p className="form-error" role="status">{onExampleSubmit ? "需要修订，请检查答案或测试结果后重新提交。" : "需要修订。真实任务须先通过后端重新进入进行中状态；浏览器状态迁移入口尚待接入。"}</p>}
      {!canSubmit && <p>当前状态暂不能提交证据，请先满足前置条件并开始任务。</p>}
      {message && <p className="form-error" role="alert"><CircleAlert size={16} />{message}</p>}
      {canSubmit && <button className="primary-button wide rounded-action" type="submit" disabled={busy}>{busy ? "提交并评价中…" : submitted ? "继续评价" : "提交证据并评价"}</button>}
    </form>}
  </SimpleModal>;
}

function TaskRow({ task, source, selected, today, onClick }: { task: Task; source: TaskSource; selected: boolean; today: string; onClick: () => void }) { return <button className={`task-row${selected ? " is-selected" : ""}`} type="button" aria-pressed={selected} onClick={onClick}><span className="task-row-number">{task.status === "PASSED" ? <CheckCircle2 size={18} /> : String(task.position).padStart(2, "0")}</span><span><strong>{task.title}</strong><small>{taskDisplayId(task, source)} · {task.estimated_minutes} 分钟 · {statusLabel(task.status)}{source === "example" && task.status !== "PASSED" && task.scheduled_date && task.scheduled_date < today ? " · 顺延" : ""}</small></span><ArrowRight size={16} /></button>; }
function EmptyState({ icon, title, text, action, onClick }: { icon: ReactNode; title: string; text: string; action?: string; onClick?: () => void }) { return <div className="empty-state"><div className="empty-icon">{icon}</div><strong>{title}</strong><p>{text}</p>{action && onClick && <button className="link-button" type="button" onClick={onClick}>{action}<ArrowRight size={15} /></button>}</div>; }
function AdjustmentModal({ accepted, realMode, onClose, onDecide }: { accepted: boolean; realMode: boolean; onClose: () => void; onDecide: (status: "accepted" | "rejected") => void }) {
  useEscapeToClose(onClose);
  return <SimpleModal title="让下一步更容易一点" description="预置演示情境：区分 print 与 return 时需要提示，建议先补一个短练习。" onClose={onClose}>
    <div className="adjustment-comparison"><div><span>原来的推荐</span><ol><li>按现有顺序继续待学任务</li><li>学习 PY-003 · 函数与测试</li></ol></div><div><span>调整后的推荐</span><ol><li>先练「分清 print 与 return」</li><li>优先继续 PY-003 · 函数与测试</li><li>其余未完成任务继续保留</li></ol></div></div>
    <p className="review-method-note">这是 Python 示例的推荐顺序调整。原任务日期、ID、完成状态和所有对话保留；补练不会代替原任务验收。约增加 3 分钟，可随时恢复原顺序。</p>
    {realMode && <p className="example-note">当前已连接真实计划。采用后仅保存示例选择，切回 Python 示例时展示；不会调整真实任务。</p>}
    <div className="adjustment-actions"><button className="secondary-button" type="button" onClick={() => onDecide("rejected")}>{accepted ? "恢复原顺序" : "保持原计划"}</button><button className="primary-button" type="button" onClick={() => accepted ? onClose() : onDecide("accepted")}>{accepted ? "完成" : "采用调整"}<ArrowRight size={15} /></button></div>
  </SimpleModal>;
}