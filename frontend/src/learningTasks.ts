import type { Task } from "./api/client";

export type EvidenceSubmission =
  | { evidence_type: "TEXT_ANSWER"; text_content: string }
  | { evidence_type: "TEST_REPORT"; test_report: { command: string; exit_code: number; summary: string; checks: { name: string; status: string; details: string }[] } };

export type ExampleProgress = {
  startDate: string;
  results: Record<string, { status: string; evidence: EvidenceSubmission; completedAt: string | null }>;
};

export function localDate(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function readExampleProgress(key: string, today: string): { progress: ExampleProgress; error: string } {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { progress: { startDate: today, results: {} }, error: "" };
    const progress = JSON.parse(raw) as ExampleProgress;
    if (!progress || typeof progress.startDate !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(progress.startDate)
      || localDate(new Date(`${progress.startDate}T12:00:00`)) !== progress.startDate
      || !progress.results || typeof progress.results !== "object" || Array.isArray(progress.results)) throw new Error("invalid progress");
    for (const result of Object.values(progress.results)) {
      if (!result || !["PASSED", "REVISION_REQUIRED"].includes(result.status)
        || (result.completedAt !== null && (typeof result.completedAt !== "string" || !Number.isFinite(Date.parse(result.completedAt))))) throw new Error("invalid result");
      const evidence = result.evidence;
      if (!evidence) throw new Error("invalid evidence");
      if (evidence.evidence_type === "TEXT_ANSWER") {
        if (typeof evidence.text_content !== "string") throw new Error("invalid answer");
      } else if (evidence.evidence_type === "TEST_REPORT") {
        const report = evidence.test_report;
        if (!report || typeof report.command !== "string" || typeof report.summary !== "string" || !Number.isInteger(report.exit_code)
          || !Array.isArray(report.checks) || report.checks.some((check) => !check || [check.name, check.status, check.details].some((value) => typeof value !== "string"))) throw new Error("invalid report");
      } else throw new Error("invalid evidence type");
    }
    return { progress, error: "" };
  } catch {
    return { progress: { startDate: today, results: {} }, error: "无法读取示例进度，原数据未覆盖。可以体验对话，暂不能保存示例成果。" };
  }
}

const pythonLessons = [
  { title: "认识 Python 变量与基础类型", objective: "用变量表示姓名、年龄和学习时长，解释字符串、整数与浮点数的区别。", deliverable: "一段示例代码和你的解释", minutes: 15 },
  { title: "编写条件判断与循环", objective: "用 for 循环遍历 1 到 10，只输出偶数，并解释判断条件。", deliverable: "代码、运行结果和实现思路", minutes: 20 },
  { title: "实现并测试一个 Python 函数", objective: "实现求和函数，验证空列表、正数和负数三种输入。", deliverable: "函数实现与测试报告", minutes: 25 },
  { title: "使用列表和字典整理学习记录", objective: "用列表保存多条学习记录，用字典描述标题和完成状态。", deliverable: "数据结构示例与遍历结果", minutes: 20 },
  { title: "读取文件并处理异常", objective: "用 with open 读取文本，处理 FileNotFoundError 并解释原因。", deliverable: "代码和文件存在、缺失时的运行结果", minutes: 25 },
  { title: "为学习记录添加自动化测试", objective: "为记录新增和完成操作编写 pytest 测试，并检查退出码。", deliverable: "测试命令、退出码与结果摘要", minutes: 25 },
];

// 每天安排三条；按原计划日期筛选，因此未通过的旧任务自然保留到次日。
export function exampleTaskCatalog(progress: ExampleProgress): Task[] {
  return pythonLessons.map((lesson, index) => {
    const date = new Date(`${progress.startDate}T12:00:00`);
    date.setDate(date.getDate() + Math.floor(index / 3));
    const scheduledDate = localDate(date);
    const result = progress.results[index + 1];
    return {
      id: index + 1, plan_version_id: 0, position: index + 1,
      scheduled_date: scheduledDate, title: lesson.title, objective: lesson.objective,
      instructions: "先动手尝试，再提交你的答案或测试结果。",
      steps: [lesson.objective, "整理学习结果并提交证据"], estimated_minutes: lesson.minutes,
      deliverable: lesson.deliverable,
      acceptance_criteria: ["文本答案不能为空；测试报告须退出码为 0 且检查通过。"],
      status: result?.status || "IN_PROGRESS", created_at: `${progress.startDate}T00:00:00`,
      completed_at: result?.completedAt || null, prerequisites: [], prerequisites_complete: true,
    };
  });
}

export function exampleTasks(progress: ExampleProgress, today: string): Task[] {
  return exampleTaskCatalog(progress).filter((task) => task.scheduled_date && task.scheduled_date <= today && (task.status !== "PASSED" || task.completed_at?.slice(0, 10) === today));
}

export function exampleDecision(evidence: EvidenceSubmission): "PASSED" | "REVISION_REQUIRED" {
  const passed = evidence.evidence_type === "TEXT_ANSWER"
    ? Boolean(evidence.text_content.trim())
    : evidence.test_report.exit_code === 0 && evidence.test_report.checks.length > 0 && evidence.test_report.checks.every((check) => check.status === "PASSED");
  return passed ? "PASSED" : "REVISION_REQUIRED";
}
