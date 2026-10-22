"""工作区课程的**参考解**（仅开发/校验用，不进 API 响应）。

每门课的参考解放在 `scripts/solutions/<slug 下划线化>.py`，文件里定义
`SOLUTIONS: dict[str, str]`，键是 **task 格的 cellId**，值是能通过该任务断言的代码
（starter 格本身的代码已经是完整可执行的，不需要参考解）。

`tests/test_workspace_content.py` 用它验证：

- 起步代码在每个任务的断言下必须**判失败**（防白给）；
- 参考解在完整重放序列下必须**全部通过**（防"单格通过、整链失败"）。

新增/修改课程 workspace 时同步维护对应文件，然后跑：

```bash
cd learn_da && .venv/Scripts/python.exe -m pytest tests/test_workspace_content.py -q
```
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SOLUTION_DIR = Path(__file__).resolve().parent / "solutions"


def _load_module(path: Path) -> dict[str, str]:
    spec = importlib.util.spec_from_file_location(f"lda_solution_{path.stem}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 损坏文件
        raise RuntimeError(f"无法加载参考解文件：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = getattr(module, "SOLUTIONS", None)
    if not isinstance(data, dict) or not data:
        raise RuntimeError(f"参考解文件缺少非空 SOLUTIONS 字典：{path}")
    return {str(key): str(value) for key, value in data.items()}


def _load_all() -> dict[str, dict[str, str]]:
    solutions: dict[str, dict[str, str]] = {}
    if not SOLUTION_DIR.is_dir():
        return solutions
    for path in sorted(SOLUTION_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        solutions[path.stem.replace("_", "-")] = _load_module(path)
    return solutions


SOLUTIONS: dict[str, dict[str, str]] = _load_all()