"""`python-functions` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": (
        "def add_bonus(score):\n"
        "    return score + 5\n"
        "\n"
        "bonus_result = add_bonus(95)\n"
        "print(bonus_result)\n"
    ),
    "c3": (
        "def total_scores(scores):\n"
        "    total = 0\n"
        "    for score in scores:\n"
        "        total = total + score\n"
        "    return total\n"
        "\n"
        "score_list = [80, 92, 76]\n"
        "total_result = total_scores(score_list)\n"
        "print(total_result)\n"
    ),
    "c4": (
        "def average_of(scores):\n"
        "    if not scores:\n"
        "        return 0.0\n"
        "    return total_scores(scores) / len(scores)\n"
        "\n"
        "def grade_of(avg):\n"
        "    if avg >= 90:\n"
        "        return 'A'\n"
        "    if avg >= 75:\n"
        "        return 'B'\n"
        "    return 'C'\n"
        "\n"
        "avg_result = average_of([80, 92, 76])\n"
        "grade_result = grade_of(avg_result)\n"
        "print(avg_result, grade_result)\n"
    ),
}