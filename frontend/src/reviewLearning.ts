import { localDate } from "./learningTasks";
import type { TaskArchive, TaskSession } from "./taskSessions";

export type ReviewOutcome = "independent" | "hinted" | "retry";
export type LearningActivity = {
  kind: "review" | "reinforcement";
  nodeId: number;
  hinted: boolean;
  priorExposure?: boolean;
  choice?: number;
  outcome?: ReviewOutcome;
  completedAt?: string;
};
export type Adjustment = { status: "accepted" | "rejected"; decidedAt: string };
export type ReviewQuestion = { prompt: string; choices: string[]; answer: number; hint: string; explanation: string };
export type KnowledgeNode = { id: number; taskId: number; title: string; chapter: string; question: ReviewQuestion };

export const knowledgeNodes: KnowledgeNode[] = [
  { id: 1, taskId: 1, title: "变量与基础类型", chapter: "基础语法", question: { prompt: '先不看笔记：\n\n```python\nage = 18\nlabel = "18"\n```\n\n这两个值的类型有什么区别？', choices: ["两者都是整数", "age 是整数，label 是字符串", "两者都是字符串"], answer: 1, hint: "观察引号。数字外面的引号会影响它的类型。", explanation: '18 是 int，"18" 是 str。内容看起来相同，不代表类型相同；字符串不能直接与整数相加。' } },
  { id: 2, taskId: 2, title: "条件判断与循环", chapter: "基础语法", question: { prompt: "先预测输出，再核对：\n\n```python\nfor n in range(1, 5):\n    if n % 2 == 0:\n        print(n)\n```\n\n程序会输出哪些数字？", choices: ["2 和 4", "1、2、3、4、5", "2、4、5"], answer: 0, hint: "range 不包含结束值，% 2 == 0 会筛选出偶数。", explanation: "range(1, 5) 产生 1 到 4。只有 2 和 4 满足条件，所以分两行输出 2、4。" } },
  { id: 3, taskId: 3, title: "函数的返回值", chapter: "函数与测试", question: { prompt: "不用运行，先说说你的判断：\n\n```python\ndef add(a, b):\n    return a + b\n\nresult = add(2, 3)\n```\n\nresult 的值是什么？", choices: ["None", "5", "函数会自动打印 5，但没有返回值"], answer: 1, hint: "return 把值交给调用者；print 才负责显示内容。这里的返回值会赋给 result。", explanation: "result 是 5。return 返回 a + b 的结果，赋值语句接住这个值；这段代码没有调用 print，不会自动打印。" } },
  { id: 4, taskId: 4, title: "列表与字典", chapter: "数据与文件", question: { prompt: '有一条记录：\n\n```python\nrecord = {"title": "学习 Python", "done": False}\n```\n\n哪一行能把它标记为完成？', choices: ['record["done"] = True', 'record["title"] = True', 'record = True'], answer: 0, hint: "需要更新字典中描述完成状态的键，而不是替换整个字典。", explanation: 'record["done"] = True 只更新完成状态，保留标题和字典本身。' } },
  { id: 5, taskId: 5, title: "文件读取与异常", chapter: "数据与文件", question: { prompt: '使用 open("notes.txt") 读取一个不存在的文件时，应针对性处理什么异常？', choices: ["ZeroDivisionError", "FileNotFoundError", "NameError"], answer: 1, hint: "异常名称通常描述问题：这里的原因是找不到文件。", explanation: "文件不存在时应针对性处理 FileNotFoundError，向用户说明缺少哪个文件，而不是掩盖所有异常。" } },
  { id: 6, taskId: 6, title: "测试结果与退出码", chapter: "函数与测试", question: { prompt: '你运行了 pytest，退出码是 1，摘要写着“1 failed”。这能作为测试通过的证据吗？', choices: ["能，只要执行过命令", "不能，应先定位失败原因并修复", "能，只要把摘要改成通过"], answer: 1, hint: "执行过测试和测试通过是两件事。判断应依据实际结果。", explanation: "不能。这个结果明确包含失败；需要检查失败用例、修复并重新运行，不能改写报告来代替执行结果。" } },
];

export const reinforcementQuestion: ReviewQuestion = {
  prompt: "先补一个小练习，再回到原来的函数任务：\n\n```python\ndef show():\n    print(3)\n\nvalue = show()\n```\n\n屏幕输出与 value 的值分别是什么？",
  choices: ["屏幕输出 3，value 也是 3", "屏幕输出 3，value 是 None", "没有输出，value 是 3"], answer: 1,
  hint: "print 负责显示。一个函数没有显式 return 时，返回值是 None。",
  explanation: "print(3) 在屏幕显示 3，但 show 没有 return，因此 value 是 None。可以把函数改成 return 3，再比较两种写法。这里不执行代码，也不会改动原任务的通过状态。",
};

export const activityQuestion = (activity: LearningActivity) => activity.kind === "reinforcement" ? reinforcementQuestion : knowledgeNodes.find((node) => node.id === activity.nodeId)!.question;
export const activityTitle = (activity: LearningActivity) => activity.kind === "reinforcement" ? "分清 print 与 return" : `复习 · ${knowledgeNodes.find((node) => node.id === activity.nodeId)!.title}`;
export const activityGroup = (session: TaskSession) => `${session.taskKey}:${session.activity ? `${session.activity.kind}:${session.activity.nodeId}` : "learning"}`;
export const outcomeLabel = (outcome: ReviewOutcome) => ({ independent: "本题独立答对", hinted: "本题借助提示或对照后答对", retry: "本题还需练习" })[outcome];
export function addDays(date: string, days: number): string {
  const value = new Date(`${date}T12:00:00`);
  value.setDate(value.getDate() + days);
  return localDate(value);
}
export const nextReviewDate = (activity: LearningActivity) => activity.completedAt ? addDays(localDate(new Date(activity.completedAt)), activity.outcome === "independent" ? 3 : 1) : null;

export function knowledgeState(node: KnowledgeNode, archive: TaskArchive, today: string) {
  const records = archive.sessions.filter((session) => session.activity?.kind === "review" && session.activity.nodeId === node.id && session.activity.completedAt)
    .sort((a, b) => b.activity!.completedAt!.localeCompare(a.activity!.completedAt!));
  const last = records[0];
  const previous = records[1];
  const seeded = !last && (node.id === 1 || node.id === 3);
  const due = last ? nextReviewDate(last.activity!) : seeded ? archive.reviewStartedOn || today : null;
  const retained = last?.activity?.outcome === "independent" && previous?.activity?.outcome === "independent" && localDate(new Date(last.activity.completedAt!)) >= nextReviewDate(previous.activity)!;
  const level = last ? retained ? "间隔后仍能应用" : last.activity!.outcome === "independent" ? "可独立完成" : last.activity!.outcome === "hinted" ? "提示下可完成" : "仍需巩固" : node.id === 1 ? "可独立完成" : node.id === 3 ? "提示下可完成" : "尚未验证";
  const reason = last ? `${outcomeLabel(last.activity!.outcome!)}。仅代表本地固定练习，不是完整能力评估。` : node.id === 1 ? "预置情境：曾独立区分整数与字符串，今天再检查一次。" : node.id === 3 ? "预置情境：区分 print 与 return 时曾需要提示，建议短练习。" : "还没有本知识点的复习结果，任务通过不会自动更新这里。";
  return { records, last, seeded, due, level, reason, isDue: Boolean(due && due <= today) };
}
