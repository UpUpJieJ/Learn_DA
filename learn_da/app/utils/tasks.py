from datetime import datetime

from app.utils.logger import log


def statistics_task():
    """
    Generate a lightweight API usage snapshot for scheduled task demos.
    """
    log.info("开始生成每日统计...")
    statistics = {
        "date": datetime.now().strftime("%Y-%m-%d-%H:%M:%S"),
        "api_calls": 7890,
    }

    log.info(f"每日统计生成完成: {statistics}")
    return statistics
