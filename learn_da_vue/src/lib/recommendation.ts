export function getRecommendationContextLesson(params: {
    lastVisitedSlug?: string | null;
}): string | undefined {
    const slug = params.lastVisitedSlug?.trim();
    return slug ? slug : undefined;
}

// =====================================================
// 建议样式映射（阶段 4 Task 2.3：RecommendationPanel 唯一实现）
//
// 三处页面（Learning / LessonDetail / Dashboard）此前各自复制了
// 近 60 行样式函数，且字段不一致（icon/emoji/iconBgClass）。
// 本函数统一提供全部字段，RecommendationPanel 只消费一份。
// =====================================================

export interface RecommendationStyle {
    containerClass: string;
    labelClass: string;
    buttonClass: string;
    badgeClass: string;
    iconBgClass: string;
    icon: string;
    emoji: string;
    label: string;
    priorityBadge: string | null;
}

export function getRecommendationStyle(rec: {
    type: string;
    priority?: number;
}): RecommendationStyle {
    const priority = rec.priority || 1;

    // 回补建议 - 橙色警示
    if (rec.type === "review_lesson") {
        return {
            containerClass: "bg-gradient-to-r from-orange-50 to-amber-50 border-2 border-orange-200 hover:border-orange-300 hover:shadow-md",
            labelClass: "text-orange-700 font-semibold",
            buttonClass: "bg-orange-600 hover:bg-orange-700 shadow-sm",
            badgeClass: "bg-orange-100 text-orange-700",
            iconBgClass: "bg-orange-100 text-orange-700",
            icon: "⚠️",
            emoji: "📖",
            label: "建议回补前置课程",
            priorityBadge: priority >= 5 ? "高优先级" : null,
        };
    }

    // 分支建议 - 紫色高亮
    if (rec.type === "branch_path") {
        return {
            containerClass: "bg-gradient-to-r from-purple-50 to-indigo-50 border-2 border-purple-200 hover:border-purple-300 hover:shadow-md",
            labelClass: "text-purple-700 font-semibold",
            buttonClass: "bg-purple-600 hover:bg-purple-700 shadow-sm",
            badgeClass: "bg-purple-100 text-purple-700",
            iconBgClass: "bg-purple-100 text-purple-700",
            icon: "🔀",
            emoji: "🎯",
            label: "学习路径分支点",
            priorityBadge: priority >= 4 ? "推荐路径" : null,
        };
    }

    // 回流建议 - 绿色温馨
    if (rec.type === "resume_session") {
        return {
            containerClass: "bg-gradient-to-r from-emerald-50 to-green-50 border-2 border-emerald-200 hover:border-emerald-300 hover:shadow-md",
            labelClass: "text-emerald-700 font-semibold",
            buttonClass: "bg-emerald-600 hover:bg-emerald-700 shadow-sm",
            badgeClass: "bg-emerald-100 text-emerald-700",
            iconBgClass: "bg-emerald-100 text-emerald-700",
            icon: "👋",
            emoji: "🔄",
            label: "欢迎回来继续学习",
            priorityBadge: null,
        };
    }

    // 顺学建议 - 蓝色默认
    return {
        containerClass: "bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-100 hover:border-blue-200 hover:shadow-md",
        labelClass: "text-blue-700 font-semibold",
        buttonClass: "bg-blue-600 hover:bg-blue-700 shadow-sm",
        badgeClass: "bg-blue-100 text-blue-700",
        iconBgClass: "bg-blue-100 text-blue-700",
        icon: "💡",
        emoji: "📚",
        label: "下一步学习建议",
        priorityBadge: null,
    };
}

