import { useEffect, useRef, useState } from "react";
import { CircleAlert, FileText, Plus, RefreshCw, X } from "lucide-react";
import { ApiRequestError, deleteResource, getJson, postJson, uploadMaterial } from "./api/client";
import type { MaterialBinding } from "./api/client";

type ParseStatus = "UPLOADED" | "QUEUED" | "PARSING" | "READY" | "FAILED";
type ProjectMaterial = MaterialBinding & {
  name: string;
  latest_version: {
    version_id: number;
    version_number: number;
    original_filename: string;
    parse_status: ParseStatus;
    parse_error_code: string | null;
    parse_error_message: string | null;
  } | null;
};
type PendingUpload = { material_id: number; version_id: number; name: string };

const labels: Record<ParseStatus, string> = {
  UPLOADED: "已上传，待解析",
  QUEUED: "排队中",
  PARSING: "正在解析",
  READY: "资料就绪",
  FAILED: "解析失败",
};

function readPending(key: string): { item: PendingUpload | null; warning: string } {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { item: null, warning: "" };
    const value = JSON.parse(raw);
    if (!value || !Number.isSafeInteger(value.material_id) || value.material_id <= 0
      || !Number.isSafeInteger(value.version_id) || value.version_id <= 0
      || typeof value.name !== "string") throw new Error("invalid pending upload");
    return { item: value, warning: "" };
  } catch {
    return { item: null, warning: "无法恢复本机待绑定记录。已绑定资料仍从服务器查询；请先核对已上传的资料 ID，避免重复上传。" };
  }
}

function errorText(error: unknown): string {
  if (error instanceof Error && error.name === "AbortError") return "请求超时或已取消";
  return error instanceof Error ? error.message : "请求失败，请稍后重试";
}

export default function ProjectMaterials({ token, userId, projectId, onBusyChange }: {
  token: string; userId: number; projectId: number; onBusyChange: (busy: boolean) => void;
}) {
  const pendingKey = "learning.pending-material." + userId + "." + projectId;
  const [initial] = useState(() => readPending(pendingKey));
  const [pending, setPending] = useState(initial.item);
  const [storageWarning, setStorageWarning] = useState(initial.warning);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState({ text: "", error: false });
  const [items, setItems] = useState<ProjectMaterial[]>([]);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [refreshIndex, setRefreshIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const alive = useRef(true);
  const operation = useRef<AbortController | null>(null);
  const stopPolling = useRef<(() => void) | null>(null);
  const listHeading = useRef<HTMLDivElement>(null);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; operation.current?.abort(); };
  }, []);

  useEffect(() => {
    if (operation.current) return;
    let stopped = false;
    let polls = 0;
    let failures = 0;
    let timer: number | undefined;
    let requestTimer: number | undefined;
    const controller = new AbortController();
    setLoading(true);
    setListError("");

    const poll = async () => {
      polls += 1;
      requestTimer = window.setTimeout(() => controller.abort(), 10_000);
      try {
        const next = await getJson<ProjectMaterial[]>(
          "/projects/" + projectId + "/materials", token, controller.signal,
        );
        if (stopped) return;
        setItems(next);
        setListError("");
        failures = 0;
        const active = next.some((item) =>
          item.latest_version?.parse_status === "QUEUED"
          || item.latest_version?.parse_status === "PARSING");
        if (active && polls < 60) timer = window.setTimeout(() => void poll(), 2_000);
        else if (active) setListError("已暂停自动查询。服务器仍可能在处理，可点击刷新状态；不需要再次上传。");
      } catch (error) {
        if (stopped) return;
        failures += 1;
        const retryable = !(error instanceof ApiRequestError) || error.retryable;
        if (controller.signal.aborted) {
          setListError("状态查询超时，已暂停。请恢复网络后刷新状态。");
        } else if (retryable && failures < 3 && polls < 60) {
          setListError("状态查询失败，稍后重试（" + failures + "/3）：" + errorText(error));
          timer = window.setTimeout(() => void poll(), 5_000);
        } else {
          setListError("状态查询已暂停：" + errorText(error) + "。请处理后手动刷新。");
        }
      } finally {
        window.clearTimeout(requestTimer);
        if (!stopped) setLoading(false);
      }
    };
    const stop = () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearTimeout(requestTimer);
      controller.abort();
    };
    stopPolling.current = stop;
    void poll();
    return () => {
      stop();
      if (stopPolling.current === stop) stopPolling.current = null;
    };
  }, [projectId, token, refreshIndex]);

  const savePending = (value: PendingUpload | null) => {
    try {
      if (value) localStorage.setItem(pendingKey, JSON.stringify(value));
      else localStorage.removeItem(pendingKey);
      if (alive.current) setStorageWarning("");
    } catch {
      if (alive.current) setStorageWarning(
        "浏览器无法更新待绑定记录。请保留当前页面和资料 ID；刷新恢复未绑定资料可能不可用。",
      );
    }
    if (alive.current) setPending(value);
  };

  const chooseFile = (next: File | null) => {
    if (!next || operation.current || pending) return;
    if (!/\.(md|markdown)$/i.test(next.name) || next.size === 0 || next.size > 10 * 1024 * 1024) {
      setFile(null);
      if (input.current) input.current.value = "";
      setMessage({ text: "请选择非空的 .md 或 .markdown 文件，大小不超过 10 MiB。", error: true });
      return;
    }
    setFile(next);
    setMessage({ text: "", error: false });
  };

  // File 从上传开始；已有 ID 从绑定或解析开始，不重新上传文件。
  const processMaterial = async (source: File | PendingUpload, needsBinding = true) => {
    if (operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 60_000);
    let stage = source instanceof File ? "上传" : needsBinding ? "绑定" : "解析提交";
    setBusy(true);
    onBusyChange(true);
    setMessage({ text: stage + "中…", error: false });
    try {
      let material: PendingUpload;
      if (source instanceof File) {
        const name = source.name.replace(/\.(md|markdown)$/i, "").trim().slice(0, 120) || "学习资料";
        const uploadFile = new File([source], source.name, { type: "text/markdown" });
        const result = await uploadMaterial(token, name, uploadFile, "", controller.signal);
        material = { material_id: result.material_id, version_id: result.version_id, name: result.name };
        // 上传响应已确认后马上保存 ID；绑定失败只重试绑定。
        savePending(material);
        if (!alive.current) return;
        setFile(null);
        if (input.current) input.current.value = "";
      } else material = source;

      if (needsBinding) {
        stage = "绑定";
        setMessage({ text: "文件已上传，正在绑定项目…", error: false });
        await postJson(
          "/projects/" + projectId + "/materials/" + material.material_id, {}, token, controller.signal,
        );
        if (!alive.current) return;
        savePending(null);
      }
      stage = "解析提交";
      setMessage({ text: "正在提交解析请求…", error: false });
      await postJson(
        "/materials/" + material.material_id + "/versions/" + material.version_id + "/parse",
        {}, token, controller.signal,
      );
      if (alive.current) setMessage({ text: "解析请求已处理，结果以服务器状态为准。", error: false });
    } catch (error) {
      if (!alive.current) return;
      const nextStep = stage === "上传"
        ? "未取得确认的资料 ID。若连接中断，结果可能未知，请先核对，避免连续重复上传。"
        : stage === "绑定"
          ? "文件已上传，使用下方「继续绑定并解析」，无需再次上传。"
          : "资料已绑定。刷新状态后，可在资料卡上继续解析，不用重新上传。";
      setMessage({ text: stage + "未确认成功：" + errorText(error) + "。" + nextStep, error: true });
    } finally {
      window.clearTimeout(timeout);
      operation.current = null;
      if (alive.current) {
        setBusy(false);
        onBusyChange(false);
        setRefreshIndex((value) => value + 1);
      }
    }
  };

  const removeMaterial = async (item: ProjectMaterial) => {
    if (operation.current || !window.confirm(
      "将「" + item.name + "」（资料 #" + item.material_id + "）从当前项目移除？\n"
      + "原文件和历史学习记录会保留，其他项目不受影响。若正在解析，后台解析会继续。",
    )) return;

    const controller = new AbortController();
    operation.current = controller;
    // 先废弃旧列表请求，避免移除成功后被迟到的 GET 再次显示。
    stopPolling.current?.();
    setLoading(false);
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    setBusy(true);
    setRemovingId(item.material_id);
    onBusyChange(true);
    setMessage({ text: "正在从项目移除「" + item.name + "」…", error: false });
    try {
      await deleteResource(
        "/projects/" + projectId + "/materials/" + item.material_id,
        token, controller.signal,
      );
      if (!alive.current) return;
      setItems((current) => current.filter((entry) => entry.material_id !== item.material_id));
      if (pending?.material_id === item.material_id) savePending(null);
      setMessage({ text: "已从当前项目移除「" + item.name + "」。原文件和历史记录仍保留。", error: false });
      listHeading.current?.focus();
    } catch (error) {
      if (alive.current) setMessage({
        text: "移除未确认成功：" + errorText(error)
          + "。请刷新状态核对；如果连接中断，服务器可能已完成移除。",
        error: true,
      });
    } finally {
      window.clearTimeout(timeout);
      operation.current = null;
      if (alive.current) {
        setBusy(false);
        setRemovingId(null);
        onBusyChange(false);
        setRefreshIndex((value) => value + 1);
      }
    }
  };

  return <>
    <div className={"material-drop-zone" + (dragging ? " is-dragging" : "")}
      onDragOver={(event) => { event.preventDefault(); if (!busy && !pending) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0] || null); }}>
      <input ref={input} type="file" accept=".md,.markdown,text/markdown,text/plain"
        disabled={busy || Boolean(pending)} onChange={(event) => chooseFile(event.target.files?.[0] || null)} />
      <button className="material-add-button" type="button" aria-label="选择 Markdown 资料"
        disabled={busy || Boolean(pending)} onClick={() => input.current?.click()}><Plus size={22} /></button>
      <strong>{file ? file.name : "拖入 Markdown 文件"}</strong>
      <span>{file ? Math.ceil(file.size / 1024) + " KB · 已选择" : "或点击加号从本机选择 · 最大 10 MiB"}</span>
    </div>
    {file && <button className="selected-file" type="button" disabled={busy}
      onClick={() => { setFile(null); if (input.current) input.current.value = ""; }}>
      <FileText size={16} /><span>{file.name}</span><X size={15} />
    </button>}
    <button className="primary-button wide rounded-action" type="button"
      disabled={!file || busy || Boolean(pending)} onClick={() => { if (file) void processMaterial(file); }}>
      {busy ? "处理中…" : "添加资料"}<Plus size={16} />
    </button>
    {message.text && <p className={message.error ? "form-error" : "upload-message"}
      role={message.error ? "alert" : "status"}>{message.text}</p>}
    {storageWarning && <p className="form-error" role="alert">{storageWarning}</p>}
    {pending && <div className="upload-result">
      <strong>文件已上传，绑定尚未确认</strong>
      <span>{pending.name} · 资料 #{pending.material_id} · 版本 #{pending.version_id}</span>
      <button className="secondary-button" type="button" disabled={busy}
        onClick={() => void processMaterial(pending)}>继续绑定并解析</button>
    </div>}
    <div ref={listHeading} tabIndex={-1} className="binding-row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
      <strong>已绑定资料 · {items.length}</strong>
      <button className="text-button" type="button" disabled={busy || loading}
        onClick={() => setRefreshIndex((value) => value + 1)}><RefreshCw size={15} />刷新状态</button>
    </div>
    {loading && <p className="material-count" role="status">正在读取资料状态…</p>}
    {listError && <p className="form-error" role="alert"><CircleAlert size={15} />{listError}</p>}
    {listError && items.length > 0 && <p className="material-count">以下保留最近一次成功查询的结果。</p>}
    {!loading && !listError && items.length === 0 && <p className="material-count">还没有已绑定的资料。</p>}
    <div aria-label="项目资料与解析状态">
      {items.map((item) => {
        const version = item.latest_version;
        const state = version?.parse_status;
        const canParse = state === "UPLOADED" || state === "FAILED";
        return <article className="binding-row" key={item.id} style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
          <FileText className="file-icon" size={20} />
          <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
            <strong>{item.name}</strong>
            <span>资料 #{item.material_id}{version ? " · 版本 #" + version.version_id + " · v" + version.version_number : ""}</span>
            {version && <span>{version.original_filename}</span>}
            <span className={"status-pill status-" + (state === "READY" ? "ready" : state === "FAILED" ? "failed" : "info")}>
              {state ? labels[state] : "版本信息缺失"}
            </span>
            {state === "FAILED" && <p className="form-error" style={{ overflowWrap: "anywhere" }}>
              {version?.parse_error_message || "解析失败，请检查文件内容后处理。"}
              {version?.parse_error_code ? "（" + version.parse_error_code + "）" : ""}
            </p>}
            {state === "READY" && <span>解析已完成。生成学习计划的入口将在后续任务接入。</span>}
            {!version && <span>请核对服务器资料记录，不要反复上传。</span>}
          </div>
          {canParse && version && <button className="secondary-button" type="button" disabled={busy}
            onClick={() => void processMaterial({
              material_id: item.material_id, version_id: version.version_id, name: item.name,
            }, false)}>{state === "FAILED" ? "重试解析" : "开始解析"}</button>}
          <button className="text-button" type="button" disabled={busy}
            aria-label={"从当前项目移除「" + item.name + "」（资料 #" + item.material_id + "）"}
            onClick={() => void removeMaterial(item)}>
            {removingId === item.material_id ? "正在移除…" : "从项目移除"}
          </button>
        </article>;
      })}
    </div>
    <p className="material-count">排队或解析时自动查询；关闭弹窗即停止查询，后台解析继续。重新打开会读取服务器最新状态。</p>
  </>;
}