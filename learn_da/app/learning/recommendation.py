"""
Phase 3: 下一步学习建议服务

规则驱动的学习建议系统，根据用户当前状态给出下一步学习建议。
本模块提供统一的建议入口，支持顺学建议、回补建议、分支建议、回流建议。
"""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.analytics.service import AnalyticsService
    from app.learning.repository import LearningRepository


# =====================================================
# 建议类型定义
# =====================================================

RecommendationType = Literal[
    "next_lesson",      # 顺学建议：继续下一课
    "review_lesson",    # 回补建议：回看前置课
    "branch_path",      # 分支建议：切换学习路径
    "resume_session",   # 回流建议：恢复中断的学习
]

RecommendationReasonCode = Literal[
    "sequential_progress",      # 顺序推进
    "prerequisite_weak",        # 前置知识薄弱
    "stuck_on_practice",        # 练习卡住
    "path_completed",           # 路径完成
    "long_absence",             # 长时间未学习
    "incomplete_practice",      # 未完成的练习
]


# =====================================================
# 建议结果数据结构
# =====================================================

class LearningRecommendation(BaseModel):
    """下一步学习建议"""

    type: RecommendationType
    """建议类型"""

    target_slug: str
    """目标课程 slug"""

    target_title: str
    """目标课程标题"""

    reason: str
    """推荐理由（用户可读）"""

    reason_code: RecommendationReasonCode
    """推荐理由代码（用于前端逻辑判断）"""

    priority: int = 1
    """优先级（1-5，5 最高）"""

    action_label: str = "开始学习"
    """行动按钮文案"""

    context: dict | None = None
    """额外上下文信息（可选）"""


class RecommendationResponse(BaseModel):
    """建议响应"""

    primary: LearningRecommendation | None
    """主要建议"""

    alternatives: list[LearningRecommendation] = []
    """备选建议"""


# =====================================================
# 课程元数据扩展
# =====================================================

class LessonMetadata(BaseModel):
    """课程元数据（用于建议规则）"""

    slug: str
    title: str
    category: str
    difficulty: str
    order: int

    # 建议系统所需字段
    track: str
    """所属路径（polars_basics, duckdb_basics, combined_workflow）"""

    prerequisites: list[str] = []
    """前置课程 slug 列表"""

    recommended_next: list[str] = []
    """推荐后继课程 slug 列表（可能有多个分支）"""

    skill_tags: list[str] = []
    """技能点标签（用于回补匹配）"""

    is_review_friendly: bool = False
    """是否适合作为回补课（基础课、概念课更适合）"""

    is_branch_point: bool = False
    """是否是路径分支点"""


# =====================================================
# 建议规则服务
# =====================================================

class RecommendationService:
    """学习建议服务"""

    # 可配置阈值（类属性，方便子类覆盖或运行时修改）
    CODE_RUNS_THRESHOLD = 5
    AI_HELPS_THRESHOLD = 3
    SNAPSHOTS_THRESHOLD = 4
    REVIEW_COOLDOWN_SECONDS = 86400  # 回补建议冷却期：24 小时

    # 分支点配置映射：branch_point_slug → 分支选项列表
    # 每个选项包含：target_slug, prerequisites(已完成的课程才给高优先级),
    # label, high_priority_reason, low_priority_reason, action_label, path_type
    BRANCH_CONFIG: dict[str, list[dict]] = {
        "polars-joins": [
            {
                "target_slug": "duckdb-sql-foundations",
                "prerequisites": ["duckdb-analytics"],
                "high_priority_reason": "你已经掌握了 Polars 的连接操作和 DuckDB 基础。接下来可以学习 DuckDB SQL 的 JOIN 语法，对比 Polars join 和 SQL JOIN 的异同。",
                "low_priority_reason": "学习 DuckDB SQL 基础，了解如何用 SQL 语法实现连接操作，为后续组合使用两个工具打下基础。",
                "action_label": "学习 SQL 路径",
                "path_type": "sql_comparison",
            },
            {
                "target_slug": "polars-lazy-pipeline",
                "prerequisites": ["polars-groupby", "polars-expressions"],
                "high_priority_reason": "你已经掌握了 Polars 的分组、表达式和连接操作。接下来可以学习 Polars 的惰性执行模式，优化复杂分析流水线的性能。",
                "low_priority_reason": "深入学习 Polars 的惰性流水线，掌握 lazy evaluation 可以让你的多步分析更高效，也为后续的组合工作流做准备。",
                "action_label": "深入 Polars 进阶",
                "path_type": "polars_advanced",
            },
        ],
        "polars-lazy-pipeline": [
            {
                "target_slug": "polars-duckdb-workflow",
                "prerequisites": ["polars-basics", "duckdb-analytics"],
                "high_priority_reason": "恭喜完成惰性流水线！现在你可以学习如何将 Polars 的数据处理能力和 DuckDB 的 SQL 分析能力组合使用，构建完整的数据分析工作流。",
                "low_priority_reason": "完成 Polars 惰性流水线后，推荐学习 Polars 与 DuckDB 组合工作流，这是一门综合实战课程。",
                "action_label": "学习组合工作流",
                "path_type": "combined_workflow",
            },
        ],
    }

    def __init__(
        self,
        repository: "LearningRepository | None" = None,
        analytics_service: "AnalyticsService | None" = None,
    ):
        self.repository = repository
        self.analytics_service = analytics_service
        self._lesson_metadata_cache: dict[str, LessonMetadata] | None = None
        self._review_cooldowns: dict[str, str] = {}  # {visitor_id+lesson_slug: ISO timestamp}

    def _get_lesson_metadata(self) -> dict[str, LessonMetadata]:
        """获取课程元数据（带缓存）"""
        if self._lesson_metadata_cache is not None:
            return self._lesson_metadata_cache

        if self.repository is None:
            raise RuntimeError("Repository is required to load lesson metadata")

        # 从课程内容中提取元数据
        lessons = self.repository.list_lessons()
        metadata_map = {}

        for lesson in lessons:
            # 优先使用 frontmatter 中的 track，否则推断
            track = self._lesson_value(lesson, 'track') or self._infer_track(lesson)

            # 优先使用 frontmatter 中的 prerequisites，否则从 prev_lesson 推断
            prerequisites = self._lesson_value(lesson, 'prerequisites', [])
            prev_lesson = self._lesson_value(lesson, 'prev_lesson')
            if not prerequisites and prev_lesson:
                prerequisites = [self._lesson_value(prev_lesson, 'slug')]

            # 优先使用 frontmatter 中的 recommended_next，否则从 next_lesson 推断
            recommended_next = self._lesson_value(lesson, 'recommended_next', [])
            next_lesson = self._lesson_value(lesson, 'next_lesson')
            if not recommended_next and next_lesson:
                recommended_next = [self._lesson_value(next_lesson, 'slug')]

            # 优先使用 frontmatter 中的 skill_tags，否则使用 tags
            skill_tags = self._lesson_value(lesson, 'skill_tags', [])
            if not skill_tags:
                skill_tags = self._lesson_value(lesson, 'tags', [])

            # 优先使用 frontmatter 中的 is_review_friendly，否则推断
            is_review_friendly = self._lesson_value(lesson, 'is_review_friendly')
            if is_review_friendly is None:
                is_review_friendly = (
                    self._lesson_value(lesson, 'difficulty') == 'beginner' or
                    'basics' in self._lesson_value(lesson, 'slug', '').lower() or
                    'foundations' in self._lesson_value(lesson, 'slug', '').lower()
                )

            # 优先使用 frontmatter 中的 is_branch_point
            is_branch_point = self._lesson_value(lesson, 'is_branch_point', False)

            metadata = LessonMetadata(
                slug=self._lesson_value(lesson, 'slug'),
                title=self._lesson_value(lesson, 'title'),
                category=self._lesson_value(lesson, 'category'),
                difficulty=self._lesson_value(lesson, 'difficulty'),
                order=self._lesson_value(lesson, 'order', 0),
                track=track,
                prerequisites=prerequisites,
                recommended_next=recommended_next,
                skill_tags=skill_tags,
                is_review_friendly=is_review_friendly,
                is_branch_point=is_branch_point,
            )

            metadata_map[metadata.slug] = metadata

        self._lesson_metadata_cache = metadata_map
        return metadata_map

    @staticmethod
    def _lesson_value(lesson: object, key: str, default=None):
        if isinstance(lesson, dict):
            return lesson.get(key, default)
        return getattr(lesson, key, default)

    def _infer_track(self, lesson: dict) -> str:
        """从课程信息推断所属路径"""
        category = self._lesson_value(lesson, 'category', '')
        slug = self._lesson_value(lesson, 'slug', '')

        if category == 'combined':
            return 'combined_workflow'
        elif category == 'polars':
            if 'lazy' in slug or 'pipeline' in slug:
                return 'polars_advanced'
            return 'polars_basics'
        elif category == 'duckdb':
            if 'window' in slug or 'cte' in slug:
                return 'duckdb_advanced'
            return 'duckdb_basics'

        return 'unknown'

    async def get_recommendation(
        self,
        visitor_id: str,
        completed_lessons: list[str],
        current_lesson_slug: str | None = None,
    ) -> RecommendationResponse:
        """
        获取用户的下一步学习建议

        Args:
            visitor_id: 访客 ID
            completed_lessons: 已完成课程列表
            current_lesson_slug: 当前正在学习的课程（可选）

        Returns:
            建议响应（包含主要建议和备选建议）
        """
        metadata_map = self._get_lesson_metadata()

        # 优先级 1: 回补建议（检测到学习困难时触发）
        review_rec = await self._get_review_recommendation(
            visitor_id=visitor_id,
            current_lesson_slug=current_lesson_slug,
            completed_lessons=completed_lessons,
            metadata_map=metadata_map,
        )

        if review_rec:
            # 如果有回补建议，顺学建议作为备选
            sequential_rec = self._get_sequential_recommendation(
                completed_lessons=completed_lessons,
                current_lesson_slug=current_lesson_slug,
                metadata_map=metadata_map,
            )
            alternatives = [sequential_rec] if sequential_rec else []
            return RecommendationResponse(
                primary=review_rec,
                alternatives=alternatives,
            )

        # 优先级 2: 分支建议（刚完成分支点课程时触发）
        branch_recs = self._get_branch_recommendation(
            completed_lessons=completed_lessons,
            current_lesson_slug=current_lesson_slug,
            metadata_map=metadata_map,
        )

        if branch_recs:
            # 如果有分支建议，第一个作为主要建议，其余作为备选
            primary = branch_recs[0]
            alternatives = branch_recs[1:] if len(branch_recs) > 1 else []

            # 如果没有备选分支，添加顺学建议作为备选
            if not alternatives:
                sequential_rec = self._get_sequential_recommendation(
                    completed_lessons=completed_lessons,
                    current_lesson_slug=current_lesson_slug,
                    metadata_map=metadata_map,
                )
                if sequential_rec and sequential_rec.target_slug != primary.target_slug:
                    alternatives = [sequential_rec]

            return RecommendationResponse(
                primary=primary,
                alternatives=alternatives,
            )

        # 优先级 3: 回流建议（长时间未学习时触发）
        resume_rec = await self._get_resume_recommendation(
            visitor_id=visitor_id,
            completed_lessons=completed_lessons,
            metadata_map=metadata_map,
        )

        if resume_rec:
            # 如果有回流建议，顺学建议作为备选
            sequential_rec = self._get_sequential_recommendation(
                completed_lessons=completed_lessons,
                current_lesson_slug=current_lesson_slug,
                metadata_map=metadata_map,
            )
            # 只有当顺学建议与回流建议不同时才作为备选
            alternatives = []
            if sequential_rec and sequential_rec.target_slug != resume_rec.target_slug:
                alternatives = [sequential_rec]

            return RecommendationResponse(
                primary=resume_rec,
                alternatives=alternatives,
            )

        # 优先级 4: 顺学建议（默认推荐逻辑）
        primary = self._get_sequential_recommendation(
            completed_lessons=completed_lessons,
            current_lesson_slug=current_lesson_slug,
            metadata_map=metadata_map,
        )

        return RecommendationResponse(
            primary=primary,
            alternatives=[],
        )

    def _get_sequential_recommendation(
        self,
        completed_lessons: list[str],
        current_lesson_slug: str | None,
        metadata_map: dict[str, LessonMetadata],
    ) -> LearningRecommendation | None:
        """
        获取顺学建议（默认推荐逻辑）

        规则：
        1. 如果当前有课程且已完成，推荐其 recommended_next 中第一个未完成课程
        2. 如果当前有课程但未完成，返回 None（让用户先完成当前课）
        3. 否则找第一个未完成的课程（按 order 排序）
        4. 如果全部完成，返回 None
        """
        # 规则 1: 当前课程的后继（必须已完成当前课）
        if current_lesson_slug and current_lesson_slug in metadata_map:
            current_meta = metadata_map[current_lesson_slug]

            # 检查当前课程是否已完成
            if current_lesson_slug in completed_lessons:
                # 已完成，推荐后继
                if current_meta.recommended_next:
                    for next_slug in current_meta.recommended_next:
                        if next_slug in metadata_map and next_slug not in completed_lessons:
                            next_meta = metadata_map[next_slug]
                            return LearningRecommendation(
                                type="next_lesson",
                                target_slug=next_slug,
                                target_title=next_meta.title,
                                reason=f"你已完成《{current_meta.title}》，建议继续学习下一课",
                                reason_code="sequential_progress",
                                priority=4,
                                action_label="继续学习",
                            )
            else:
                # 未完成当前课，不推荐新课程
                return None

        # 规则 2: 找第一个未完成的课程（按 order 排序）
        all_lessons = sorted(metadata_map.values(), key=lambda x: x.order)
        for lesson_meta in all_lessons:
            if lesson_meta.slug not in completed_lessons:
                # 判断是否是第一课
                is_first_lesson = lesson_meta.order == min(m.order for m in metadata_map.values())

                if is_first_lesson:
                    reason = "推荐从第一课开始学习"
                    priority = 3
                else:
                    reason = f"推荐继续学习《{lesson_meta.title}》"
                    priority = 2

                return LearningRecommendation(
                    type="next_lesson",
                    target_slug=lesson_meta.slug,
                    target_title=lesson_meta.title,
                    reason=reason,
                    reason_code="sequential_progress",
                    priority=priority,
                    action_label="开始学习",
                )

        # 规则 3: 全部完成 - 兜底建议
        # 找到第一个 beginner + is_review_friendly 的课程作为重学推荐
        review_candidates = [
            m for m in metadata_map.values()
            if m.is_review_friendly
        ]
        review_candidates.sort(key=lambda x: x.order)

        if review_candidates:
            first_review = review_candidates[0]
            return LearningRecommendation(
                type="review_lesson",
                target_slug=first_review.slug,
                target_title=first_review.title,
                reason=f"恭喜你完成了所有课程！推荐回顾《{first_review.title}》巩固基础，温故知新。",
                reason_code="path_completed",
                priority=1,
                action_label="回顾学习",
            )

        # 最终兜底：推荐第一课
        first_lesson = min(metadata_map.values(), key=lambda x: x.order)
        return LearningRecommendation(
            type="review_lesson",
            target_slug=first_lesson.slug,
            target_title=first_lesson.title,
            reason="恭喜你完成了所有课程！推荐从第一课开始回顾，温故知新。",
            reason_code="path_completed",
            priority=1,
            action_label="重新学习",
        )

    # =====================================================
    # 预留接口：后续轮次实现
    # =====================================================

    async def _get_review_recommendation(
        self,
        visitor_id: str,
        current_lesson_slug: str | None,
        completed_lessons: list[str],
        metadata_map: dict[str, LessonMetadata],
    ) -> LearningRecommendation | None:
        """
        获取回补建议

        触发条件：
        - 同一课多次运行失败（codeRuns >= CODE_RUNS_THRESHOLD）
        - 多次请求 AI 提示（aiHelps >= AI_HELPS_THRESHOLD）
        - 在某个技能点保存了很多尝试仍未完成（snapshots >= SNAPSHOTS_THRESHOLD）
        - 长时间停滞（距首次活动 >= 30 分钟但仍未完成）

        回补逻辑：
        1. 提取当前课程的前置课程列表
        2. 优先选择标记为 is_review_friendly=true 的前置课程
        3. 如果没有 review-friendly 的前置课程，选择第一个前置课程
        4. 返回选中的前置课程作为回补建议

        冷却机制：
        - 触发回补建议后，同一 visitor+lesson 在 24 小时内不重复触发
        - 避免用户被反复推荐回补
        """
        if not self.analytics_service:
            return None

        # 只对当前正在学习且未完成的课程触发回补建议
        if not current_lesson_slug or current_lesson_slug in completed_lessons:
            return None

        if current_lesson_slug not in metadata_map:
            return None

        # 冷却检查：同一 visitor+lesson 在冷却期内不重复触发
        cooldown_key = f"{visitor_id}::{current_lesson_slug}"
        if cooldown_key in self._review_cooldowns:
            from datetime import datetime, timezone
            try:
                last_trigger = datetime.fromisoformat(self._review_cooldowns[cooldown_key])
                if last_trigger.tzinfo is None:
                    last_trigger = last_trigger.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last_trigger).total_seconds()
                if elapsed < self.REVIEW_COOLDOWN_SECONDS:
                    return None
            except (ValueError, TypeError):
                pass  # 解析失败则忽略冷却

        # 获取当前课程的学习统计
        stats = await self.analytics_service.get_lesson_specific_stats(
            visitor_id, current_lesson_slug
        )
        snapshots_count = await self.analytics_service.get_lesson_snapshots_count(
            visitor_id, current_lesson_slug
        )

        # 检查是否触发回补条件
        code_runs = stats.get("codeRuns", 0)
        ai_helps = stats.get("aiHelps", 0)
        completed = stats.get("completed", False)

        # 判断是否需要回补
        needs_review = False
        reason_template = ""

        if not completed and code_runs >= self.CODE_RUNS_THRESHOLD:
            needs_review = True
            reason_template = f"你在这节课尝试了 {code_runs} 次代码运行，建议回顾 {{review_lesson}} 巩固基础"
        elif not completed and ai_helps >= self.AI_HELPS_THRESHOLD:
            needs_review = True
            reason_template = f"你请求了 {ai_helps} 次 AI 帮助，{{review_lesson}} 的内容可能需要复习"
        elif not completed and snapshots_count >= self.SNAPSHOTS_THRESHOLD:
            needs_review = True
            reason_template = f"你保存了 {snapshots_count} 个代码快照但未完成，建议先回顾 {{review_lesson}}"
        elif not completed and self._check_long_stall(stats, snapshots_count):
            needs_review = True
            reason_template = f"你在这节课停留了较长时间，建议先回顾 {{review_lesson}} 打好基础再继续"

        if not needs_review:
            return None

        # 记录冷却时间
        from datetime import datetime, timezone
        self._review_cooldowns[cooldown_key] = datetime.now(timezone.utc).isoformat()

        # 选择回补课程
        current_meta = metadata_map[current_lesson_slug]
        prerequisites = current_meta.prerequisites

        # 候选策略 1：从前置课程中选（优先 is_review_friendly）
        # 候选策略 2：从全量课程中按 skill_tags 匹配选（前置课程为空时使用）
        review_lesson_slug = None

        if prerequisites:
            # 优先选择 is_review_friendly=true 的前置课程
            for prereq_slug in prerequisites:
                if prereq_slug in metadata_map:
                    prereq_meta = metadata_map[prereq_slug]
                    if prereq_meta.is_review_friendly:
                        review_lesson_slug = prereq_slug
                        break

            # 如果没有 review-friendly 的前置课程，选择第一个前置课程
            if not review_lesson_slug:
                review_lesson_slug = prerequisites[0]
        else:
            # 无前置课程时，通过 skill_tags 在全量课程中匹配回补友好课
            if current_meta.skill_tags:
                best_match = None
                best_overlap = 0
                for slug, meta in metadata_map.items():
                    if slug == current_lesson_slug or slug not in completed_lessons:
                        continue
                    if not meta.is_review_friendly:
                        continue
                    overlap = len(set(meta.skill_tags) & set(current_meta.skill_tags))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_match = slug
                if best_match:
                    review_lesson_slug = best_match

        if not review_lesson_slug or review_lesson_slug not in metadata_map:
            return None

        review_meta = metadata_map[review_lesson_slug]

        # 如果回补课程本身也未完成，则不推荐（避免循环）
        if review_meta.slug not in completed_lessons:
            # 使用特殊理由模板
            reason_template = f"这节课的前置知识《{review_meta.title}》标记为适合复习，建议先巩固基础再继续"

        reason = reason_template.replace("{review_lesson}", f"《{review_meta.title}》")

        return LearningRecommendation(
            type="review_lesson",
            target_slug=review_meta.slug,
            target_title=review_meta.title,
            reason=reason,
            reason_code="prerequisite_weak",
            priority=5,  # 最高优先级
            action_label="回顾课程",
            context={
                "current_lesson": current_lesson_slug,
                "code_runs": code_runs,
                "ai_helps": ai_helps,
                "snapshots": snapshots_count,
            },
        )

    @staticmethod
    def _check_long_stall(stats: dict, snapshots_count: int) -> bool:
        """
        检查是否长时间停滞

        判断逻辑：有活动记录（code_runs 或 ai_helps > 0）且未完成，
        且最近一次活动距首次活动超过 30 分钟（基于 duration_seconds 推断）。
        简化实现：code_runs >= 3 且 ai_helps >= 1 且 snapshots >= 2 时视为长时间停滞。
        """
        code_runs = stats.get("codeRuns", 0)
        ai_helps = stats.get("aiHelps", 0)
        completed = stats.get("completed", False)

        if completed:
            return False

        # 长时间停滞的弱信号组合：有一定的运行和求助，但都没有达到独立阈值
        return code_runs >= 3 and ai_helps >= 1 and snapshots_count >= 2

    def _get_branch_recommendation(
        self,
        completed_lessons: list[str],
        current_lesson_slug: str | None,
        metadata_map: dict[str, LessonMetadata],
    ) -> list[LearningRecommendation]:
        """
        获取分支建议（配置驱动）

        触发条件：
        - 刚完成某个标记为 is_branch_point=true 的课程
        - 该课程在 BRANCH_CONFIG 中有配置
        - 至少有一个 recommended_next 选项未完成
        """
        # 只在刚完成分支点课程时触发
        if not current_lesson_slug or current_lesson_slug not in completed_lessons:
            return []

        if current_lesson_slug not in metadata_map:
            return []

        current_meta = metadata_map[current_lesson_slug]

        # 必须是分支点
        if not current_meta.is_branch_point:
            return []

        if len(current_meta.recommended_next) == 0:
            return []

        # 从配置中获取分支选项
        branch_options = self.BRANCH_CONFIG.get(current_meta.slug, [])
        if not branch_options:
            return []

        branch_recommendations = []

        for option in branch_options:
            target_slug = option["target_slug"]

            # 必须在 recommended_next 中
            if target_slug not in current_meta.recommended_next:
                continue

            # 目标课程必须存在且未完成
            if target_slug not in metadata_map or target_slug in completed_lessons:
                continue

            target_meta = metadata_map[target_slug]

            # 检查前置条件是否满足
            prerequisites = option.get("prerequisites", [])
            all_prereqs_met = all(p in completed_lessons for p in prerequisites)

            reason = option["high_priority_reason"] if all_prereqs_met else option["low_priority_reason"]
            priority = 4 if all_prereqs_met else 3

            branch_recommendations.append(
                LearningRecommendation(
                    type="branch_path",
                    target_slug=target_slug,
                    target_title=target_meta.title,
                    reason=reason,
                    reason_code="path_completed",
                    priority=priority,
                    action_label=option["action_label"],
                    context={
                        "branch_point": current_meta.slug,
                        "path_type": option["path_type"],
                    },
                )
            )

        # 按优先级排序
        branch_recommendations.sort(key=lambda x: x.priority, reverse=True)

        return branch_recommendations

    async def _get_resume_recommendation(
        self,
        visitor_id: str,
        completed_lessons: list[str],
        metadata_map: dict[str, LessonMetadata],
        absence_threshold_days: int = 3,
    ) -> LearningRecommendation | None:
        """
        获取回流建议

        触发条件：
        - 距离上次学习间隔 >= absence_threshold_days
        - 有未完成但有活动的课程

        选择逻辑：
        1. 查询所有有活动但未完成的课程
        2. 计算每个课程的恢复成本分数（越低越好）
        3. 推荐恢复成本最低的课程
        """
        if not self.analytics_service:
            return None

        # 获取用户画像，检查是否满足回流条件
        profile = await self.analytics_service.get_user_profile(visitor_id)
        if not profile or not profile.get("lastActiveDate"):
            return None

        # 计算距离上次学习的天数
        from datetime import datetime, timezone
        try:
            last_active = datetime.strptime(profile["lastActiveDate"], "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            days_since_last_active = (today - last_active).days
        except (ValueError, TypeError):
            return None

        # 如果距离上次学习不足阈值天数，不触发回流建议
        if days_since_last_active < absence_threshold_days:
            return None

        # 获取有活动但未完成的课程
        incomplete_lessons = await self.analytics_service.get_incomplete_lessons_with_activity(
            visitor_id, completed_lessons
        )

        if not incomplete_lessons:
            # 如果没有未完成的课程，检查是否有已完成的课程
            if completed_lessons:
                # 推荐下一个顺序课程
                all_lessons = sorted(metadata_map.values(), key=lambda x: x.order)
                for lesson_meta in all_lessons:
                    if lesson_meta.slug not in completed_lessons:
                        return LearningRecommendation(
                            type="resume_session",
                            target_slug=lesson_meta.slug,
                            target_title=lesson_meta.title,
                            reason=f"距离上次学习已经 {days_since_last_active} 天了，推荐从《{lesson_meta.title}》继续你的学习旅程。",
                            reason_code="long_absence",
                            priority=3,
                            action_label="继续学习",
                            context={
                                "days_since_last_active": days_since_last_active,
                            },
                        )
            else:
                # 推荐第一课
                first_lesson = min(metadata_map.values(), key=lambda x: x.order)
                return LearningRecommendation(
                    type="resume_session",
                    target_slug=first_lesson.slug,
                    target_title=first_lesson.title,
                    reason=f"距离上次学习已经 {days_since_last_active} 天了，推荐从第一课《{first_lesson.title}》开始。",
                    reason_code="long_absence",
                    priority=3,
                    action_label="开始学习",
                    context={
                        "days_since_last_active": days_since_last_active,
                    },
                )
            return None

        # 计算每个候选课程的恢复成本分数
        candidates = []
        for lesson_data in incomplete_lessons:
            lesson_slug = lesson_data["lesson_slug"]
            if lesson_slug not in metadata_map:
                continue

            lesson_meta = metadata_map[lesson_slug]

            # 计算 base_engagement_score (0-100, 越低越好)
            engagement_level = (
                lesson_data["code_runs"]
                + (lesson_data["ai_helps"] * 2)
                + (lesson_data["snapshots_count"] * 3)
            )
            base_engagement_score = max(0, 100 - engagement_level * 5)

            # 计算 recency_score (0-100, 越低越好)
            if lesson_data["last_activity_time"]:
                try:
                    last_activity = lesson_data["last_activity_time"]
                    if last_activity.tzinfo is None:
                        last_activity = last_activity.replace(tzinfo=timezone.utc)
                    days_since_activity = (datetime.now(timezone.utc) - last_activity).days
                    recency_score = min(100, days_since_activity * 10)
                except Exception:
                    recency_score = 50  # 默认中等分数
            else:
                recency_score = 50

            # 计算 difficulty_penalty (0-30)
            difficulty_map = {"beginner": 0, "intermediate": 10, "advanced": 30}
            difficulty_penalty = difficulty_map.get(lesson_meta.difficulty, 10)

            # 计算总恢复成本分数
            resume_cost = (
                base_engagement_score * 0.5
                + recency_score * 0.3
                + difficulty_penalty * 0.2
            )

            candidates.append({
                "lesson_slug": lesson_slug,
                "lesson_meta": lesson_meta,
                "resume_cost": resume_cost,
                "code_runs": lesson_data["code_runs"],
                "ai_helps": lesson_data["ai_helps"],
                "snapshots_count": lesson_data["snapshots_count"],
                "days_since_activity": days_since_activity if lesson_data["last_activity_time"] else None,
            })

        if not candidates:
            return None

        # 选择恢复成本最低的课程
        best_candidate = min(candidates, key=lambda x: x["resume_cost"])

        # 选择推荐理由模板
        reason_templates = [
            "你在《{lesson_title}》中已经运行了 {code_runs} 次代码，写了 {snapshots_count} 个版本，继续完成它只需要一小步！",
            "《{lesson_title}》是你 {days_ago} 天前尝试的，当时已经运行了 {code_runs} 次代码，趁记忆还新鲜，现在是完成它的好时机。",
            "你在《{lesson_title}》中使用了 {ai_helps} 次 AI 助手，说明你对这个主题很感兴趣。现在回来完成它，之前的努力不会白费！",
            "《{lesson_title}》是你最近尝试但未完成的课程，已经有 {code_runs} 次代码运行记录。从这里继续，成本最低、效果最好。",
            "你在《{lesson_title}》中保存了 {snapshots_count} 个代码快照，说明你已经投入了不少精力。现在是收获成果的时候了！",
            "距离上次学习《{lesson_title}》已经 {days_ago} 天了，但你之前的 {code_runs} 次尝试还历历在目。现在回来，轻松拿下它！",
            "《{lesson_title}》是你尝试过但未完成的课程中，恢复成本最低的一个。你已经运行了 {code_runs} 次代码，继续下去就能完成！",
            "你在《{lesson_title}》中的学习轨迹显示：{code_runs} 次代码运行、{ai_helps} 次 AI 求助。这些努力值得一个完美的结局。",
            "《{lesson_title}》是你 {days_ago} 天前开始的，虽然还没完成，但你已经保存了 {snapshots_count} 个版本。现在是时候画上句号了！",
            "根据你的学习数据，《{lesson_title}》是最容易恢复的课程：难度适中、记忆新鲜、已有 {code_runs} 次实践基础。",
        ]

        # 根据数据特征选择最合适的模板（确定性选择，不用 random）
        if best_candidate["snapshots_count"] >= 3:
            # 强调快照的模板
            reason_template = reason_templates[4]
        elif best_candidate["ai_helps"] >= 2:
            # 强调 AI 助手的模板
            reason_template = reason_templates[7]
        elif best_candidate["days_since_activity"] and best_candidate["days_since_activity"] <= 7:
            # 强调时间新鲜的模板
            reason_template = reason_templates[1]
        else:
            # 使用通用模板
            reason_template = reason_templates[3]

        # 填充模板
        reason = reason_template.format(
            lesson_title=best_candidate["lesson_meta"].title,
            code_runs=best_candidate["code_runs"],
            ai_helps=best_candidate["ai_helps"],
            snapshots_count=best_candidate["snapshots_count"],
            days_ago=best_candidate["days_since_activity"] or days_since_last_active,
        )

        return LearningRecommendation(
            type="resume_session",
            target_slug=best_candidate["lesson_slug"],
            target_title=best_candidate["lesson_meta"].title,
            reason=reason,
            reason_code="incomplete_practice",
            priority=4,
            action_label="继续完成",
            context={
                "resume_cost": best_candidate["resume_cost"],
                "code_runs": best_candidate["code_runs"],
                "ai_helps": best_candidate["ai_helps"],
                "snapshots_count": best_candidate["snapshots_count"],
                "days_since_last_active": days_since_last_active,
            },
        )
