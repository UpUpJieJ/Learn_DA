"""课程数据集的可复现性守卫（详设 §7，lint L6/L7）。

数据集一等公民之后，"数据悄悄变了"是最难查的一类 bug：课程正文里的数字、
断言里的 ``ref``、学员看到的结果三者会对不上。这里把约束钉死：

1. 生成器是确定性的（同代码两次生成字节一致）；
2. 仓库里提交的文件 == 生成器产物（改数据必须改生成器并重新生成）；
3. ``manifest.json`` 的 sha256 / 行数 / 字节数与实际文件一致；
4. 单课数据集总量 ≤ 5MB，且只用 UTF-8 + LF（沙箱是 Linux）。
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

LEARN_DA_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = LEARN_DA_ROOT / "scripts" / "build_datasets.py"
DATASET_DIR = LEARN_DA_ROOT / "content" / "datasets" / "ecommerce"
MAX_DATASET_BYTES = 5 * 1024 * 1024


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_datasets", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load_builder()


@pytest.fixture(scope="module")
def artifacts(builder):
    return builder.build_all()


def _rows(name: str) -> list[dict[str, str]]:
    text = (DATASET_DIR / name).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def test_generator_is_deterministic(builder):
    assert builder.build_all() == builder.build_all()


def test_committed_files_match_generator(builder, artifacts, tmp_path):
    problems = builder.write_artifacts(tmp_path, artifacts)
    assert problems == []
    for name, payload in artifacts.items():
        committed = (DATASET_DIR / name).read_bytes()
        assert committed == payload, f"{name} 与生成器产物不一致（重新跑 build_datasets.py）"


def test_manifest_matches_files(artifacts):
    manifest = json.loads(artifacts["manifest.json"].decode("utf-8"))
    assert manifest["seed"] == json.loads((DATASET_DIR / "manifest.json").read_text("utf-8"))["seed"]
    for name, entry in manifest["files"].items():
        payload = (DATASET_DIR / name).read_bytes()
        assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
        assert entry["bytes"] == len(payload)
        if name.endswith(".csv"):
            assert entry["rows"] == len(_rows(name))


def test_dataset_size_and_line_endings(artifacts):
    total = sum(len(payload) for payload in artifacts.values())
    assert total <= MAX_DATASET_BYTES, f"数据集总大小 {total} 超过 5MB（lint L6）"
    for name, payload in artifacts.items():
        assert b"\r\n" not in payload, f"{name} 出现 CRLF，沙箱是 Linux，只允许 LF"


def test_orders_amount_matches_arithmetic():
    rows = _rows("orders.csv")
    assert len(rows) == 5000
    for row in rows[:200]:
        expected = round(float(row["unit_price"]) * int(row["quantity"]) * float(row["discount"]), 2)
        assert abs(expected - float(row["amount"])) <= 0.01


def test_orders_reference_existing_dimensions():
    orders = _rows("orders.csv")
    customers = {row["customer_id"]: row for row in _rows("customers.csv")}
    products = {row["product_id"]: row for row in _rows("products.csv")}
    assert len(customers) == 800
    assert len(products) == 120
    for row in orders:
        assert row["customer_id"] in customers
        assert row["product_id"] in products
        # region 是客户维度，必须与 customers 一致（课程正文会用到这个口径）
        assert row["region"] == customers[row["customer_id"]]["region"]
        assert row["order_date"][:4] == "2025"


def test_csv_headers_are_stable(artifacts):
    expected = {
        "orders.csv": [
            "order_id", "customer_id", "product_id", "region", "channel",
            "quantity", "unit_price", "discount", "amount", "order_date", "refunded",
        ],
        "customers.csv": ["customer_id", "name", "city", "region", "segment", "signup_date"],
        "products.csv": ["product_id", "category", "unit_price", "cost", "launch_date"],
    }
    for name, columns in expected.items():
        header = artifacts[name].decode("utf-8").splitlines()[0]
        assert header.split(",") == columns


def test_check_mode_passes_on_committed_data(builder):
    assert builder.write_artifacts(DATASET_DIR, builder.build_all(), check=True) == []


def test_check_mode_detects_drift(builder, artifacts, tmp_path):
    for name, payload in artifacts.items():
        (tmp_path / name).write_bytes(payload)
    (tmp_path / "orders.csv").write_bytes(b"order_id\nO000001\n")
    problems = builder.write_artifacts(tmp_path, artifacts, check=True)
    assert any("orders.csv" in problem for problem in problems)