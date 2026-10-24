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