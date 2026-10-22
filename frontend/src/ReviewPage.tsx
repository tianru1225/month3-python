import { ArrowRight, BookOpen, CheckCircle2, RefreshCw, Sparkles } from "lucide-react";
import type { TaskArchive } from "./taskSessions";
import { knowledgeNodes, knowledgeState, outcomeLabel } from "./reviewLearning";

export function AdjustmentNotice({ archive, onPreview }: { archive: TaskArchive; onPreview: () => void }) {
  const status = archive.adjustment?.status;
  return <div className="adjustment-notice">
    <span className="review-icon"><Sparkles size={19} /></span>
    <div><span className="review-eyebrow">学习调整 · 预置演示</span><strong>{status === "accepted" ? "先分清 print 与 return，再继续函数任务" : status === "rejected" ? "已保持原来的学习顺序" : "遇到卡点，可以先补一个小练习"}</strong><p>{status === "accepted" ? "已加入 Python 示例的今日推荐。原任务与已有记录继续保留。" : status === "rejected" ? "建议仍可回看，不会自动调整任务。" : "演示情境：函数返回值还需要提示。先看看调整前后，再决定是否采用。"}</p></div>
    <button className="secondary-button" type="button" onClick={onPreview}>{status ? "查看调整" : "预览建议"}<ArrowRight size={15} /></button>
  </div>;
}

type Props = {
  archive: TaskArchive; today: string; realMode: boolean;
  onReview: (id: number) => void; onOriginal: (id: number) => void;
  onSession: (id: string) => void;
};

export default function ReviewPage({ archive, today, realMode, onReview, onOriginal, onSession }: Props) {
  const nodes = knowledgeNodes.map((node) => ({ node, state: knowledgeState(node, archive, today) }));
  const due = nodes.filter(({ state }) => state.isDue);
  return <div className="review-page">
    <p className="review-demo-note"><Sparkles size={15} /><span>Python 功能演示 · 含预置情境 · 仅本机保存。{realMode ? "与当前真实计划分开，不读取或修改其掌握度。" : "结果来自固定题目，不代表完整能力评估。"}</span></p>
    <section aria-labelledby="review-due-title"><div className="review-section-heading"><div><h3 id="review-due-title">今天温习一点</h3><p>{due.length ? `${due.length} 个知识点建议复习，按自己的节奏完成。` : "今天建议的复习已完成，也可以自选知识点练习。"}</p></div><span>{today}</span></div>
      <div className="review-due-grid">{due.map(({ node, state }) => <article className="surface-card review-due-card" key={node.id}><span className="review-eyebrow">{state.seeded ? "预置复习" : "到期复习"} · 约 3 分钟</span><h3>{node.title}</h3><p>{state.reason}</p><div><span>来自 PY-{String(node.taskId).padStart(3, "0")}</span><button className="primary-button" type="button" onClick={() => onReview(node.id)}>开始复习<ArrowRight size={15} /></button></div></article>)}{!due.length && <div className="review-all-done"><CheckCircle2 size={22} /><span>这次复习已留下记录，下一次从实际完成日期安排。</span></div>}</div>
    </section>
    <section aria-labelledby="knowledge-title"><div className="review-section-heading"><div><h3 id="knowledge-title">我的知识点</h3><p>掌握表现和复习时间分开看；任务提交通过，不会自动变成“已掌握”。</p></div><span>{nodes.length} 个示例知识点</span></div>
      <div className="knowledge-list">{nodes.map(({ node, state }) => <article className="surface-card knowledge-card" key={node.id}>
        <div className="knowledge-main"><div className="knowledge-heading"><span className="review-icon"><BookOpen size={18} /></span><div><small>{node.chapter} · PY-{String(node.taskId).padStart(3, "0")}</small><h3>{node.title}</h3></div></div><p>{state.reason}</p><div className="knowledge-status"><span className={`mastery-label ${state.level === "尚未验证" ? "unverified" : ""}`}>{state.level}</span>{state.seeded && <span>预置演示</span>}{state.last && <span>最近核对 {new Date(state.last.activity!.completedAt!).toLocaleDateString("zh-CN")}</span>}{state.isDue ? <span className="review-due-label"><RefreshCw size={12} />建议复习</span> : state.due && <span>下次建议 {state.due}</span>}</div></div>
        <div className="knowledge-actions"><button className="secondary-button" type="button" onClick={() => onReview(node.id)}>{state.isDue ? "去复习" : "练一题"}<ArrowRight size={14} /></button><button className="link-button" type="button" onClick={() => onOriginal(node.taskId)}>回看原任务</button></div>
        {state.records.length > 0 && <details className="task-session-history"><summary>复习证据 · {state.records.length} 次</summary>{state.records.map((record) => <button type="button" key={record.id} onClick={() => onSession(record.id)}><span>{outcomeLabel(record.activity!.outcome!)}</span><span>{new Date(record.activity!.completedAt!).toLocaleString("zh-CN")}<ArrowRight size={14} /></span></button>)}</details>}
      </article>)}</div>
    </section>
    <p className="review-method-note">演示规则：固定题独立答对后 3 天再复习；使用提示、看过当日反馈或答错后 1 天再练。同一知识点只保留一个下一次建议时间，历史证据继续保留。这些间隔仅用于展示交互。</p>
  </div>;
}
