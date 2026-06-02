import type { LessonCategory } from "@/types/api";

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
  color: "blue" | "yellow" | "purple";
  route: string;
  lessonCount: number;
}

export const platformCopy = {
  name: "Learn DA",
  title: "Pandas / SQL 迁移到 Polars / DuckDB",
  shortTitle: "迁移学习平台",
  heroTitle: "从 Pandas / SQL",
  heroTitleHighlight: "迁移到 Polars / DuckDB",
  heroSubtitle:
    "面向已有 Pandas 或 SQL 基础的学习者，用课程、练习、Playground 和学习教练，把熟悉的分析习惯迁移到 Polars / DuckDB。",
  currentScope: "当前版本聚焦 11 节核心课程与 3 条迁移路径",
  expansionHint: "后续可扩展更多数据分析迁移方向。",
};

export const learningTracks: LearningTrackMeta[] = [
  {
    key: "polars",
    label: "Pandas → Polars",
    shortLabel: "Polars",
    subtitle: "现代高性能 DataFrame",
    description:
      "首批开放专题。学习高性能 DataFrame 数据处理、表达式系统、惰性执行与分组聚合。",
    targetAudience: "有 Pandas 基础，想迁移到更快更现代的 DataFrame 工具",
    learningOutcome:
      "能独立用 Polars 完成数据读取、清洗、聚合、连接等常见分析流程",
    recommendedStart: "先从 Polars Basics 第 1 课开始",
    tags: ["DataFrame", "惰性执行", "高性能", "Python"],
    color: "blue",
    route: "/learn?category=polars",
    lessonCount: 6,
  },
  {
    key: "duckdb",
    label: "SQL → DuckDB",
    shortLabel: "DuckDB",
    subtitle: "嵌入式分析数据库",
    description:
      "首批开放专题。学习在本地进程中用 SQL 查询 CSV、Parquet 与内存数据集。",
    targetAudience: "有 SQL 基础，想在 Python 环境中直接跑分析查询",
    learningOutcome:
      "能用 DuckDB 在本地查询 CSV/Parquet，完成聚合、窗口函数、子查询等操作",
    recommendedStart: "先从 DuckDB Foundations 第 1 课开始",
    tags: ["SQL", "OLAP", "零配置", "文件分析"],
    color: "yellow",
    route: "/learn?category=duckdb",
    lessonCount: 4,
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
    lessonCount: 1,
  },
];

export const currentTrackKeys = learningTracks.map((track) => track.key);

export const learningTrackMeta = Object.fromEntries(
  learningTracks.map((track) => [track.key, track]),
) as Record<LessonCategory, LearningTrackMeta>;
