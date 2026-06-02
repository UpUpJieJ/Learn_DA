export function getRecommendationContextLesson(params: {
    lastVisitedSlug?: string | null;
}): string | undefined {
    const slug = params.lastVisitedSlug?.trim();
    return slug ? slug : undefined;
}
