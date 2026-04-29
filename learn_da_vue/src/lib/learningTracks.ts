import type { LessonCategory } from "@/types/api";

export interface LearningTrackMeta {
  key: LessonCategory;
  label: string;
  shortLabel: string;
  subtitle: string;
  description: string;
  tags: string[];
  color: "blue" | "yellow" | "purple";
  route: string;
  lessonCount: number;
}

export const platformCopy = {
  name: "Learn DA",
  title: "数据分析学习平台",
  shortTitle: "数据分析平台",
  currentScope: "当前已开放 Polars、DuckDB 与组合实战专题",
  expansionHint: "后续可扩展 Pandas、SQL 基础、数据可视化、特征工程等方向。",
};

export const learningTracks: LearningTrackMeta[] = [
  {
    key: "polars",
    label: "Polars",
    shortLabel: "Polars",
    subtitle: "现代 DataFrame 库",
    description:
      "首批开放专题。学习高性能 DataFrame 数据处理、表达式系统、惰性执行与分组聚合。",
    tags: ["DataFrame", "惰性执行", "高性能", "Python"],
    color: "blue",
    route: "/learn?category=polars",
    lessonCount: 12,
  },
  {
    key: "duckdb",
    label: "DuckDB",
    shortLabel: "DuckDB",
    subtitle: "嵌入式分析数据库",
    description:
      "首批开放专题。学习在本地进程中用 SQL 查询 CSV、Parquet 与内存数据集。",
    tags: ["SQL", "OLAP", "零配置", "文件分析"],
    color: "yellow",
    route: "/learn?category=duckdb",
    lessonCount: 10,
  },
  {
    key: "combined",
    label: "组合实战",
    shortLabel: "实战",
    subtitle: "数据分析工作流",
    description:
      "把 Polars 与 DuckDB 放进完整分析流程，练习数据读取、转换、查询和结果输出。",
    tags: ["数据管道", "综合案例", "工作流"],
    color: "purple",
    route: "/learn?category=combined",
    lessonCount: 8,
  },
];

export const currentTrackKeys = learningTracks.map((track) => track.key);

export const learningTrackMeta = Object.fromEntries(
  learningTracks.map((track) => [track.key, track]),
) as Record<LessonCategory, LearningTrackMeta>;
