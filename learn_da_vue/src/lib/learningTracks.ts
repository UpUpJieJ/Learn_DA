import type { LessonCategory } from "@/types/api";

/**
 * 兜底文案：仅在 catalog API 不可用时用于首页/学习页的降级展示。
 * catalog 是唯一事实源，这里的 label/description 等纯文案字段需与
 * content/catalog.yml 保持方向一致，但不再承载会过期的数据（如课程数）。
 */
export interface LearningTrackMeta {
  key: LessonCategory;
  label: string;
  shortLabel: string;
  subtitle: string;
  description: string;
  targetAudience: string;
  learningOutcome: string;
  recommendedStart: string;
  tags: string[];
  color: "blue" | "yellow" | "purple" | "emerald";
  route: string;
}

export const platformCopy = {
  name: "Learn DA",
  title: "交互式数据分析学习平台",
  shortTitle: "数据分析学习平台",
  heroTitle: "边学边练",
  heroTitleHighlight: "数据分析与编程实战",
  heroSubtitle:
    "以数据分析为核心的学习平台，用课程、练习、Playground 和学习教练，把概念理解落到可运行的代码上。",
  currentScope: "持续更新的数据分析课程与学习路径",
  expansionHint: "可按需扩展更多数据分析与编程主题。",
};

export const learningTracks: LearningTrackMeta[] = [
  {
    key: "polars",
    label: "Polars 基础",
    shortLabel: "Polars",
    subtitle: "现代高性能 DataFrame",
    description:
      "首批开放专题。学习高性能 DataFrame 数据处理、表达式系统、惰性执行与分组聚合。",
    targetAudience: "想学习高性能 DataFrame 与现代数据处理的学习者",
    learningOutcome:
      "能独立用 Polars 完成数据读取、清洗、聚合、连接等常见分析流程",
    recommendedStart: "先从 Polars Basics 第 1 课开始",
    tags: ["DataFrame", "惰性执行", "高性能", "Python"],
    color: "blue",
    route: "/learn?category=polars",
  },
  {
    key: "duckdb",
    label: "DuckDB 基础",
    shortLabel: "DuckDB",
    subtitle: "嵌入式分析数据库",
    description:
      "首批开放专题。学习在本地进程中用 SQL 查询 CSV、Parquet 与内存数据集。",
    targetAudience: "想在 Python 环境中直接跑分析查询的学习者",
    learningOutcome:
      "能用 DuckDB 在本地查询 CSV/Parquet，完成聚合、窗口函数、子查询等操作",
    recommendedStart: "先从 DuckDB Foundations 第 1 课开始",
    tags: ["SQL", "OLAP", "零配置", "文件分析"],
    color: "yellow",
    route: "/learn?category=duckdb",
  },
  {
    key: "combined",
    label: "组合实战",
    shortLabel: "实战",
    subtitle: "Polars + DuckDB 工作流",
    description:
      "把 Polars 与 DuckDB 放进完整分析流程，练习数据读取、转换、查询和结果输出。",
    targetAudience: "已了解 Polars 和 DuckDB 基本用法，想学习如何组合使用",
    learningOutcome:
      "能在真实分析场景中灵活切换 Polars 和 DuckDB，构建完整数据管道",
    recommendedStart: "建议先完成 Polars 或 DuckDB 基础路径",
    tags: ["数据管道", "综合案例", "工作流"],
    color: "purple",
    route: "/learn?category=combined",
  },
  {
    key: "python",
    label: "Python 基础",
    shortLabel: "Python",
    subtitle: "编程入门",
    description:
      "面向初学者的 Python 语法和思维入门，可作为更多学习路线的起点。",
    targetAudience: "想从零开始学习 Python 编程的学习者",
    learningOutcome:
      "能读懂并写出基本的 Python 函数与数据结构操作",
    recommendedStart: "先从 Python 基础第 1 课开始",
    tags: ["Python", "编程基础", "入门"],
    color: "emerald",
    route: "/learn?category=python",
  },
];

export const currentTrackKeys = learningTracks.map((track) => track.key);

export const learningTrackMeta = Object.fromEntries(
  learningTracks.map((track) => [track.key, track]),
) as Record<LessonCategory, LearningTrackMeta>;
