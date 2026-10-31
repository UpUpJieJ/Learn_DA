/** One denominator across overview/report: distinct attempted tasks, all history. */
export function formatFirstTryRate(summary: { tasksFirstTry: number; tasksAttempted: number } | null): string {
    if (!summary || !Number.isFinite(summary.tasksAttempted) || summary.tasksAttempted <= 0) return "—";
    return `${Math.round(Math.min(100, Math.max(0, summary.tasksFirstTry / summary.tasksAttempted * 100)))}%`;
}
