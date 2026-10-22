import type { Task } from "./api/client";
import { activityQuestion, activityTitle, knowledgeNodes } from "./reviewLearning";
import type { Adjustment, LearningActivity } from "./reviewLearning";

export type TaskSource = "example" | "real";
export type LearningMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  state?: "streaming" | "complete" | "stopped" | "error";
  error?: string;
  origin?: "demo" | "model";
  guideStep?: number;
  action?: "next";
};
export type TaskSession = {
  id: string;
  taskKey: string;
  source: TaskSource;
  task: Task;
  startedAt: string;
  updatedAt: string;
  mode: "demo" | "model";
  step: number;
  draft: string;
  messages: LearningMessage[];
  activity?: LearningActivity;
};
export type SessionUpdate = Pick<TaskSession, "mode" | "step" | "draft" | "messages" | "activity">;
export type TaskArchive = { version: 1; selectedId: string | null; sessions: TaskSession[]; reviewStartedOn?: string; adjustment?: Adjustment };
export type GuideStep = { title: string; explanation: string; example: string; exercise: string; hint: string };

export const emptyArchive = (): TaskArchive => ({ version: 1, selectedId: null, sessions: [] });
export const taskKey = (task: Task, source: TaskSource) => `${source}:${task.plan_version_id}:${task.id}`;
export const taskDisplayId = (task: Task, source: TaskSource) => source === "example" ? `PY-${String(task.id).padStart(3, "0")}` : `#${task.id}`;

const guides: Record<number, GuideStep[]> = {
  1: [
    { title: "认识变量", explanation: "变量是一个有名字的位置，用来保存一个值。等号右边是值，左边是名字。", example: 'name = "小林"\nprint(name)', exercise: "试着写一行代码，把你的姓名保存到 name 中。", hint: "文字需要用引号包起来，例如 name = \"小林\"。变量名本身不用引号。" },
    { title: "分清基础类型", explanation: "str 保存文字，int 保存整数，float 保存带小数点的数。用 type() 可以查看类型。", example: 'name = "小林"\nage = 18\nhours = 1.5\nprint(type(name), type(age), type(hours))', exercise: '猜一猜：18 和 "18" 的类型一样吗？先说出你的判断，再运行验证。', hint: '18 是整数，"18" 是字符串。有没有引号，会改变这个值的类型。' },
    { title: "完成一张学习名片", explanation: "把刚学的三种类型用在同一个小程序里，并解释你选择这些类型的原因。", example: 'name = "小林"\nage = 18\nhours = 1.5\nprint(f"{name}，{age} 岁，今天学习 {hours} 小时")', exercise: "改成你自己的数据，提交代码、运行结果，以及三种类型的解释。", hint: "姓名用字符串，年龄用整数，带小数的学习时长用浮点数。完成后点击顶部「提交成果」。" },
  ],
  2: [
    { title: "让代码重复执行", explanation: "for 循环依次取出一组值。range(1, 11) 从 1 开始，到 11 之前结束。", example: "for number in range(1, 11):\n    print(number)", exercise: "运行这段代码，记录第一个和最后一个数字。为什么最后不是 11？", hint: "range 的结束值不包含在结果中；循环里的语句需要缩进。" },
    { title: "用条件筛选偶数", explanation: "% 计算余数。一个整数除以 2 的余数为 0，就能被 2 整除。", example: "number = 4\nif number % 2 == 0:\n    print(number)", exercise: "分别把 number 改成 3 和 4，观察是否输出。", hint: "== 用来比较，= 用来赋值。if 后面的冒号和下一行缩进都不能少。" },
    { title: "组合循环与判断", explanation: "把条件判断放进循环，就能逐个检查每个数字。", example: "for number in range(1, 11):\n    if number % 2 == 0:\n        print(number)", exercise: "运行程序，确认输出 2、4、6、8、10；解释每一层缩进的含义，再提交成果。", hint: "先循环取数字，再判断余数，最后只输出满足条件的数字。" },
  ],
  3: [
    { title: "定义一个函数", explanation: "函数把一段操作放到一个名字下面。参数接收输入，return 把结果交还给调用者。", example: "def add(a, b):\n    return a + b\n\nprint(add(2, 3))", exercise: "观察返回值，再解释 print 和 return 的作用有什么不同。", hint: "print 显示内容；return 结束当前函数并把一个值返回给调用者。" },
    { title: "把列表中的数加起来", explanation: "从 0 开始，用一个变量累计列表中每个数字。空列表不进入循环，所以返回 0。", example: "def total(values):\n    result = 0\n    for value in values:\n        result += value\n    return result", exercise: "试着手算 total([2, -1, 3])，再运行程序对照。", hint: "累计值会依次变成 2、1、4；return 要放在循环之后。" },
    { title: "验证边界情况", explanation: "测试既要检查普通输入，也要检查空列表和负数。", example: "assert total([]) == 0\nassert total([1, 2, 3]) == 6\nassert total([-2, 1]) == -1", exercise: "实际运行三项测试，再通过「提交成果」填写测试命令、退出码和结果摘要。", hint: "此页面不运行代码。请填入你实际执行得到的结果，不要把示例输出当作执行证据。" },
  ],
  4: [
    { title: "用字典描述一条记录", explanation: "字典用键和值描述一件事情，例如标题和完成状态。", example: 'record = {"title": "学习变量", "done": False}\nprint(record["title"])', exercise: "为你今天正在学习的内容创建一条记录。", hint: "标题是字符串，完成状态可以用布尔值 True 或 False。" },
    { title: "用列表保存多条记录", explanation: "列表可以按顺序保存多个字典，再用循环逐条读取。", example: 'records = [\n    {"title": "学习变量", "done": True},\n    {"title": "练习循环", "done": False},\n]\nfor record in records:\n    print(record["title"])', exercise: "增加第三条记录，再打印所有未完成的任务标题。", hint: '可以在循环中写 if not record["done"] 来筛选未完成项。' },
    { title: "更新学习状态", explanation: "找到对应记录后，可以为字典中的某个键重新赋值。", example: 'records[0]["done"] = True\nprint(records[0])', exercise: "把一项未完成任务改为完成，提交更新前后的输出以及你的解释。", hint: "列表索引从 0 开始。先确认索引对应哪一条记录，再修改它。" },
  ],
  5: [
    { title: "读取一个文本文件", explanation: "with 会在代码块结束后关闭文件。读取中文文本时显式指定 UTF-8 编码。", example: 'with open("notes.txt", encoding="utf-8") as file:\n    content = file.read()\nprint(content)', exercise: "自己创建 notes.txt，写入一句学习笔记，再读取它。", hint: "相对路径从程序的当前工作目录查找文件，不一定是代码文件所在目录。" },
    { title: "处理文件不存在", explanation: "文件不存在时会抛出 FileNotFoundError，可以用 try/except 给出清楚的反馈。", example: 'try:\n    with open("notes.txt", encoding="utf-8") as file:\n        print(file.read())\nexcept FileNotFoundError:\n    print("请先创建 notes.txt")', exercise: "将文件临时改名，重新执行并观察提示。", hint: "只捕获这里预期的文件缺失异常，避免掩盖其他错误。" },
    { title: "验证两个执行分支", explanation: "文件存在和缺失时，都应该得到你预期的行为。", example: '# 场景一：文件存在，输出内容\n# 场景二：文件缺失，显示友好提示', exercise: "提交代码及两个场景的实际输出，并解释异常处理的作用。", hint: "说明哪些语句可能报错，以及 except 为什么只在文件缺失时执行。" },
  ],
  6: [
    { title: "让记录操作可测试", explanation: "先把新增记录封装成函数，让输入和结果清楚可见。", example: 'def add_record(records, title):\n    records.append({"title": title, "done": False})', exercise: "调用函数新增一条记录，检查标题和初始状态。", hint: "测试前用一个新的空列表，避免上一次操作留下的数据影响结果。" },
    { title: "用断言描述预期", explanation: "pytest 会收集 test_ 开头的测试函数。assert 用来声明应该成立的条件。", example: 'def test_add_record():\n    records = []\n    add_record(records, "学习 Python")\n    assert len(records) == 1\n    assert records[0]["done"] is False', exercise: "再写一个测试，验证完成操作会把 done 改成 True。", hint: "每个测试先准备数据，再执行操作，最后检查结果。" },
    { title: "执行并整理测试报告", explanation: "在包含测试文件的项目目录运行 pytest，记录实际的通过/失败结果。", example: 'pytest -q', exercise: "提交实际命令、退出码、测试摘要，以及新增和完成操作分别验证了什么。", hint: "非零退出码不能当作通过；这份演示不会替你执行测试。" },
  ],
};

export function taskGuide(task: Task, source: TaskSource): GuideStep[] {
  if (source === "example" && guides[task.id]) return guides[task.id];
  return [
    { title: "理解任务", explanation: task.objective, example: "", exercise: "先用自己的话说说这个任务要解决什么问题。", hint: `关注最终交付内容：${task.deliverable}` },
    { title: "逐步尝试", explanation: task.instructions, example: "", exercise: task.steps[0] || "从最小的一步开始，记录你的尝试和遇到的问题。", hint: "先缩小问题，再验证一个小结果。此处是固定引导，具体疑问可切换模型问答。" },
    { title: "整理成果", explanation: task.acceptance_criteria.join("\n"), example: "", exercise: `整理并提交：${task.deliverable}`, hint: "聊天引导不会改变真实任务状态，提交与评价继续由后端决定。" },
  ];
}

export function guideMessage(task: Task, source: TaskSource, step: number): string {
  const guide = taskGuide(task, source)[step];
  return `## ${step + 1}. ${guide.title}\n\n${guide.explanation}${guide.example ? `\n\n\`\`\`python\n${guide.example}\n\`\`\`` : ""}\n\n**轮到你试一试**\n${guide.exercise}`;
}

export function demoReply(task: Task, source: TaskSource, step: number, message: LearningMessage): string {
  const guide = taskGuide(task, source)[step];
  if (message.action === "next") return guideMessage(task, source, step);
  if (/提示|不懂|不会|解释|例子/.test(message.content)) return `我们慢一点，先抓住这一点：\n\n${guide.hint}${guide.example ? `\n\n可以对照这个例子：\n\n\`\`\`python\n${guide.example}\n\`\`\`` : ""}\n\n${guide.exercise}`;
  if (/[?？]|为什么|什么|怎么|区别/.test(message.content)) return `这份演示的当前知识点是「${guide.title}」。\n\n${guide.explanation}\n\n${guide.hint}\n\n这是固定脚本，暂时不能理解所有自由提问。需要针对这个问题展开回答，可以切换顶部的「模型问答」。`;
  return `已记录你的尝试。请对照当前练习检查：\n\n${guide.exercise}\n\n**自查提示**\n${guide.hint}\n\n准备好后可以${step < taskGuide(task, source).length - 1 ? "点击「下一步」" : "点击顶部「提交成果」"}。演示不会执行代码或判定答案的正确性。`;
}

export function createTaskSession(task: Task, source: TaskSource): TaskSession {
  const now = new Date().toISOString();
  return {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
    taskKey: taskKey(task, source), source, task, startedAt: now, updatedAt: now,
    mode: "demo", step: 0, draft: "",
    messages: [{ id: 1, role: "assistant", content: guideMessage(task, source, 0), state: "complete", origin: "demo", guideStep: 0 }],
  };
}

export function createActivitySession(task: Task, activity: LearningActivity): TaskSession {
  const session = createTaskSession(task, "example");
  return { ...session, activity, messages: [{ id: 1, role: "assistant", state: "complete", origin: "demo", content: `## ${activityTitle(activity)}\n\n${activityQuestion(activity).prompt}\n\n先选择你的判断，也可以在输入框写下思路。核对后会保存本次固定题目的结果；不会改变原任务状态。${activity.priorExposure ? "\n\n本日已看过本题提示或反馈，本轮作为巩固练习记录。" : ""}` }] };
}

export function readTaskArchive(key: string): { archive: TaskArchive; error: string } {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { archive: emptyArchive(), error: "" };
    const value = JSON.parse(raw) as TaskArchive;
    if (value.version !== 1 || !Array.isArray(value.sessions)) throw new Error("invalid archive");
    if (value.reviewStartedOn !== undefined && (typeof value.reviewStartedOn !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value.reviewStartedOn) || !Number.isFinite(Date.parse(value.reviewStartedOn)))) throw new Error("invalid review date");
    if (value.adjustment && (!["accepted", "rejected"].includes(value.adjustment.status) || !Number.isFinite(Date.parse(value.adjustment.decidedAt)))) throw new Error("invalid adjustment");
    const ids = new Set<string>();
    for (const session of value.sessions) {
      if (!session) throw new Error("invalid session");
      const task = session.task;
      if (!session || !task || typeof session.id !== "string" || ids.has(session.id) || !["example", "real"].includes(session.source)
        || !Number.isSafeInteger(task.id) || task.id < 1 || !Number.isSafeInteger(task.plan_version_id)
        || (session.source === "example" ? task.plan_version_id !== 0 : task.plan_version_id < 1)
        || [task.title, task.objective, task.instructions, task.deliverable, task.status].some((item) => typeof item !== "string")
        || !Array.isArray(task.steps) || !task.steps.every((item) => typeof item === "string")
        || !Array.isArray(task.acceptance_criteria) || !task.acceptance_criteria.every((item) => typeof item === "string")
        || session.taskKey !== taskKey(task, session.source) || !["demo", "model"].includes(session.mode)
        || !Number.isInteger(session.step) || session.step < 0 || session.step >= taskGuide(task, session.source).length
        || typeof session.draft !== "string" || !Number.isFinite(Date.parse(session.startedAt)) || !Number.isFinite(Date.parse(session.updatedAt))
        || !Array.isArray(session.messages) || session.messages.some((message) => !message || !Number.isSafeInteger(message.id) || !["user", "assistant"].includes(message.role) || typeof message.content !== "string")) throw new Error("invalid session");
      ids.add(session.id);
      if (session.activity) {
        const activity = session.activity;
        const node = knowledgeNodes.find((item) => item.id === activity.nodeId);
        if (session.source !== "example" || !node || node.taskId !== task.id || !["review", "reinforcement"].includes(activity.kind)
          || (activity.kind === "reinforcement" && node.id !== 3) || typeof activity.hinted !== "boolean"
          || (activity.priorExposure !== undefined && typeof activity.priorExposure !== "boolean") || (activity.priorExposure && !activity.hinted) || session.mode !== "demo"
          || (activity.choice !== undefined && (!Number.isInteger(activity.choice) || activity.choice < 0 || activity.choice >= activityQuestion(activity).choices.length))) throw new Error("invalid activity");
        if (activity.completedAt !== undefined) {
          const expected = activity.choice === activityQuestion(activity).answer ? activity.hinted ? "hinted" : "independent" : "retry";
          if (!Number.isFinite(Date.parse(activity.completedAt)) || activity.choice === undefined || activity.outcome !== expected) throw new Error("invalid review result");
        } else if (activity.outcome !== undefined) throw new Error("incomplete review result");
      }
      session.messages = session.messages.map((message) => message.state === "streaming" ? { ...message, state: "stopped" } : message);
    }
    if (typeof value.selectedId !== "string" || !ids.has(value.selectedId)) value.selectedId = null;
    return { archive: value, error: "" };
  } catch {
    return { archive: emptyArchive(), error: "无法读取本机学习记录，原数据未覆盖。本次对话仅在当前页面暂存。" };
  }
}
