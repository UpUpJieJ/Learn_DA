"""依赖版本锁定的一致性守卫。

沙箱镜像（执行用户代码）与后端（工作区断言 DSL 求值）必须用同一份
polars / duckdb 版本，否则同一个脚本在本地通过、线上判定为不通过。
这里把「三处版本」锁在一起：

1. ``Dockerfile.sandbox`` 里的 ``ARG PIP_*_VERSION``
2. ``pyproject.toml`` 的 ``==`` 精确约束
3. 当前解释器里实际安装的版本

任何一处改动而没同步，测试就会失败——升级流程是：三处一起改，
再跑 ``tests/test_workspace_content.py``（13 课起步代码必失败 + 参考解必全过）复核。
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

import pytest

LEARN_DA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LEARN_DA_ROOT.parent
SANDBOX_DOCKERFILE = LEARN_DA_ROOT / "Dockerfile.sandbox"
PYPROJECT = LEARN_DA_ROOT / "pyproject.toml"

# 沙箱里执行、后端里判定，必须完全一致的包
LOCKSTEP_PACKAGES = ("polars", "duckdb")


def _sandbox_pins() -> dict[str, str]:
    text = SANDBOX_DOCKERFILE.read_text(encoding="utf-8")
    pins: dict[str, str] = {}
    for match in re.finditer(r"^ARG PIP_(\w+)_VERSION=(\S+)$", text, re.MULTILINE):
        pins[match.group(1).lower()] = match.group(2)
    return pins


def _pyproject_requirements() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def _pinned_in_pyproject(package: str) -> str | None:
    pattern = re.compile(rf"^{package}==")
    for requirement in _pyproject_requirements():
        if pattern.match(requirement):
            return requirement.split("==", 1)[1]
    return None


def test_sandbox_pins_every_lockstep_package() -> None:
    pins = _sandbox_pins()
    for package in LOCKSTEP_PACKAGES:
        assert package in pins, (
            f"Dockerfile.sandbox 缺少 PIP_{package.upper()}_VERSION 锁定"
        )
        assert re.fullmatch(r"\d+\.\d+\.\d+", pins[package]), (
            f"PIP_{package.upper()}_VERSION 必须是精确版本，实际 {pins[package]!r}"
        )


@pytest.mark.parametrize("package", LOCKSTEP_PACKAGES)
def test_pyproject_uses_exact_pin(package: str) -> None:
    assert _pinned_in_pyproject(package) is not None, (
        f"pyproject.toml 里 {package} 必须是 == 精确约束，不能是 >="
    )


@pytest.mark.parametrize("package", LOCKSTEP_PACKAGES)
def test_sandbox_pin_matches_pyproject(package: str) -> None:
    sandbox_version = _sandbox_pins().get(package)
    backend_version = _pinned_in_pyproject(package)
    assert sandbox_version == backend_version, (
        f"{package} 版本漂移：沙箱 {sandbox_version} vs 后端 {backend_version}"
    )


@pytest.mark.parametrize("package", LOCKSTEP_PACKAGES)
def test_installed_version_matches_pins(package: str) -> None:
    module = pytest.importorskip(package)
    assert getattr(module, "__version__", None) == _pinned_in_pyproject(package), (
        f"当前环境安装的 {package} 与锁定版本不一致，先 uv sync"
    )


def test_sandbox_and_backend_share_python_minor() -> None:
    """沙箱与后端镜像都基于 python:3.12-slim，Python 次版本不应分叉。"""
    import sys

    dockerfiles = [SANDBOX_DOCKERFILE, LEARN_DA_ROOT / "Dockerfile"]
    bases = {
        path.name: re.search(
            r"^ARG PYTHON_BASE_IMAGE=(\S+)$", path.read_text(encoding="utf-8"), re.MULTILINE
        )
        for path in dockerfiles
    }
    for name, match in bases.items():
        assert match is not None, f"{name} 未声明 PYTHON_BASE_IMAGE"
        assert "3.12" in match.group(1), f"{name} 基础镜像不是 3.12：{match.group(1)}"
    assert sys.version_info[:2] == (3, 12), (
        f"本地解释器应与镜像一致（3.12），实际 {sys.version_info[:2]}"
    )


def test_dataset_budget_does_not_exceed_runner_limit() -> None:
    """后端的课程数据集预算不能大于 Runner 的请求上限。

    两边各有一份数字：``learn_da/app/workspace/content.py`` 的
    ``MAX_TOTAL_DATASET_BYTES`` 与 ``learn_da_runner/runner/settings.py`` 的
    ``RUNNER_SESSION_MAX_DATASET_BYTES``。后端更大时，课程能通过 content_lint，
    却在运行时被 Runner 以 ``invalid_session_request`` 拒绝——学习者只会看到
    一句看不懂的报错。这里把两个数字锁在一起。
    """
    from app.workspace.content import MAX_DATASET_BYTES, MAX_TOTAL_DATASET_BYTES

    runner_settings_path = REPO_ROOT / "learn_da_runner" / "runner" / "settings.py"
    text = runner_settings_path.read_text(encoding="utf-8")
    match = re.search(
        r"^\s*RUNNER_SESSION_MAX_DATASET_BYTES:\s*int\s*=\s*([\d_]+)", text, re.MULTILINE
    )
    assert match is not None, "learn_da_runner/runner/settings.py 缺少该配置"
    runner_limit = int(match.group(1).replace("_", ""))

    assert MAX_DATASET_BYTES <= runner_limit, (
        f"单文件预算 {MAX_DATASET_BYTES} 大于 Runner 上限 {runner_limit}"
    )
    assert MAX_TOTAL_DATASET_BYTES <= runner_limit, (
        f"总量预算 {MAX_TOTAL_DATASET_BYTES} 大于 Runner 上限 {runner_limit}"
    )


def test_backend_session_timeout_exceeds_runner_session_timeout() -> None:
    """后端整段重放超时必须比 Runner 的更长，否则先超时的是后端。

    Runner 侧超时会返回结构化的 ``timeout`` 结论（哪个单元格超时、跑了多久）；
    后端先超时只会抛 ``RunnerUnavailableError``，学习者看到的是「执行服务不可用」，
    完全误导。``learn_da/config/settings.py`` 的默认值必须大于 Runner 的默认值。
    """
    from config.settings import Settings

    backend_default = Settings.model_fields["RUNNER_SESSION_TIMEOUT_SECONDS"].default

    runner_settings_path = REPO_ROOT / "learn_da_runner" / "runner" / "settings.py"
    text = runner_settings_path.read_text(encoding="utf-8")
    match = re.search(
        r"^\s*RUNNER_SESSION_TIMEOUT_SECONDS:\s*int\s*=\s*(\d+)", text, re.MULTILINE
    )
    assert match is not None, "learn_da_runner/runner/settings.py 缺少该配置"
    runner_default = int(match.group(1))

    assert backend_default > runner_default, (
        "后端 RUNNER_SESSION_TIMEOUT_SECONDS 默认值 "
        f"({backend_default}) 必须大于 Runner 的 ({runner_default})"
    )