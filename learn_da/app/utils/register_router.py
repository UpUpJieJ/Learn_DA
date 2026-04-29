import importlib
import os
from pathlib import Path

from fastapi import FastAPI, APIRouter

from config.settings import settings
from .logger import log


def auto_register_routers(
    app: FastAPI,
    main_router: APIRouter,
    app_root: str = "app",
) -> None:
    """
    自动发现并注册 app 目录下所有子应用的 router
    """
    log.debug("开始自动注册路由")
    # 从当前文件向上查找直到找到项目根目录（包含main.py的目录）
    current_path = Path(__file__).parent
    while current_path.parent != current_path:  # 防止无限循环
        if (current_path.parent / "main.py").exists():
            project_root = current_path.parent
            break
        current_path = current_path.parent
    else:
        # 如果没找到main.py，则使用当前文件所在目录的上两级作为项目根目录
        project_root = Path(__file__).parent.parent.parent

    root_path = project_root / app_root
    # log.debug(f"项目根目录: {project_root}")
    # log.debug(f"搜索路径: {root_path}")

    if not root_path.exists():
        log.error(f"指定的app目录不存在: {root_path}")
        return

    enabled_modules = set(settings.enabled_app_modules)
    count = 0
    module_name = ""
    for path in root_path.rglob("router.py"):
        # 计算模块名
        try:
            relative = path.relative_to(project_root)
            parts = relative.parts
            if len(parts) < 3:
                continue

            top_level_module = parts[1]
            if top_level_module.startswith("_"):
                continue
            if enabled_modules and top_level_module not in enabled_modules:
                continue

            module_name = str(relative.with_suffix("")).replace(os.sep, ".")

            module = importlib.import_module(module_name)
            router = getattr(module, "router", None)
            if router is None:
                log.warning(f"{module_name} 中没有 router 对象，跳过")
                continue

            main_router.include_router(router)
            log.debug(f"已加载子路由：{module_name}")
            count += 1
        except Exception as e:
            log.error(f"加载 {module_name} 失败：{e}")

    log.info(f"路由注册完成，共加载 {count} 个路由模块")
