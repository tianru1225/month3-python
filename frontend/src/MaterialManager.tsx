import { useEffect, useRef, useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { ApiRequestError, deleteResource, getJson } from "./api/client";

type MaterialItem = {
  material_id: number;
  name: string;
  created_at: string;
  deletion_pending: boolean;
  blockers: string[];
};
type MaterialPage = { items: MaterialItem[]; next_before_id: number | null };

export default function MaterialManager({ token, userId, onBusyChange }: {
  token: string; userId: number; onBusyChange: (busy: boolean) => void;
}) {
  const [items, setItems] = useState<MaterialItem[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const alive = useRef(true);
  const query = useRef<AbortController | null>(null);
  const write = useRef<AbortController | null>(null);
  const heading = useRef<HTMLDivElement>(null);

  const load = async (before: number | null = null) => {
    if (write.current) return;
    query.current?.abort();
    const controller = new AbortController();
    query.current = controller;
    const timer = window.setTimeout(() => controller.abort(), 15_000);
    setLoading(true);
    setError("");
    try {
      const page = await getJson<MaterialPage>(
        "/materials?limit=50" + (before ? "&before_id=" + before : ""),
        token, controller.signal,
      );
      if (!alive.current || query.current !== controller) return;
      setItems((current) => before
        ? [...current, ...page.items.filter((item) => !current.some((old) => old.material_id === item.material_id))]
        : page.items);
      setCursor(page.next_before_id);
    } catch (reason) {
      if (alive.current && query.current === controller) {
        setError(controller.signal.aborted ? "查询超时，请刷新重试。" : reason instanceof Error ? reason.message : "读取失败");
      }
    } finally {
      window.clearTimeout(timer);
      if (alive.current && query.current === controller) {
        query.current = null;
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
      query.current?.abort();
      write.current?.abort();
    };
  }, [token]);

  const clearPendingUpload = (materialId: number): string => {
    try {
      const prefix = "learning.pending-material." + userId + ".";
      for (let index = localStorage.length - 1; index >= 0; index -= 1) {
        const key = localStorage.key(index);
        if (!key?.startsWith(prefix)) continue;
        const value = JSON.parse(localStorage.getItem(key) || "null");
        if (value?.material_id === materialId) localStorage.removeItem(key);
      }
      return "";
    } catch {
      return " 本机待绑定记录未能完全清理；服务器结果不受影响。";
    }
  };

  const remove = async (item: MaterialItem) => {
    if (write.current || item.blockers.length || !window.confirm(
      (item.deletion_pending ? "继续清理" : "彻底删除") + "「" + item.name + "」（资料 #" + item.material_id + "）？\n"
      + "将删除这份资料的全部版本、原文件及解析结果，无法撤销。\n"
      + "若已被项目或学习历史使用，服务器会拒绝删除。",
    )) return;
    const controller = new AbortController();
    write.current = controller;
    query.current?.abort();
    query.current = null;
    setLoading(false);
    setBusyId(item.material_id);
    onBusyChange(true);
    setNotice("");
    setError("");
    const timer = window.setTimeout(() => controller.abort(), 30_000);
    try {
      await deleteResource("/materials/" + item.material_id, token, controller.signal);
      if (!alive.current) return;
      setItems((current) => current.filter((value) => value.material_id !== item.material_id));
      setNotice("资料及文件已删除。" + clearPendingUpload(item.material_id));
      heading.current?.focus();
    } catch (reason) {
      if (alive.current) {
        if (reason instanceof ApiRequestError && reason.status === 404) {
          setItems((current) => current.filter((value) => value.material_id !== item.material_id));
          setNotice("这份资料当前已不存在或不可访问。" + clearPendingUpload(item.material_id));
        } else {
          setNotice("删除未确认完成：" + (controller.signal.aborted
            ? "请求超时。"
            : reason instanceof Error ? reason.message : "请求失败。")
            + " 列表将重新查询；若显示清理未完成，可重试清理。");
        }
      }
    } finally {
      window.clearTimeout(timer);
      write.current = null;
      if (alive.current) {
        setBusyId(null);
        onBusyChange(false);
        void load();
      }
    }
  };

  return <>
    <div className="binding-row" ref={heading} tabIndex={-1} style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
      <strong>我上传的资料</strong>
      <button className="text-button" type="button" disabled={busyId !== null || loading}
        onClick={() => void load()}><RefreshCw size={15} />刷新</button>
    </div>
    <p className="material-count">包含未绑定和已从项目移除的资料。仍被使用的资料会显示不能删除的原因。</p>
    {notice && <p className="upload-message" role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error} 当前列表可能是上一次查询结果。</p>}
    {loading && <p role="status">正在查询…</p>}
    {!loading && !error && !items.length && <p className="material-count">没有已上传的资料。</p>}
    {items.map((item) => <article className="binding-row" key={item.material_id}
      style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 180, overflowWrap: "anywhere" }}>
        <strong>{item.name}</strong>
        <span>资料 #{item.material_id}</span>
        {item.deletion_pending && <p className="form-error">清理尚未完成，资料已停止使用，请重试清理。</p>}
        {item.blockers.map((reason) => <p className="material-count" key={reason}>{reason}</p>)}
      </div>
      <button className="text-button" type="button" disabled={busyId !== null || item.blockers.length > 0}
        aria-label={(item.deletion_pending ? "重试清理" : "彻底删除") + "「" + item.name + "」"}
        onClick={() => void remove(item)}>
        <Trash2 size={15} />{busyId === item.material_id ? "清理中…" : item.deletion_pending ? "重试清理" : "彻底删除"}
      </button>
    </article>)}
    {cursor !== null && <button className="secondary-button" type="button"
      disabled={loading || busyId !== null} onClick={() => void load(cursor)}>加载更多</button>}
    <p className="material-count">“从项目移除”只解除绑定；这里的“彻底删除”会清理服务器文件。网络中断时先刷新确认结果，不重复上传。</p>
  </>;
}