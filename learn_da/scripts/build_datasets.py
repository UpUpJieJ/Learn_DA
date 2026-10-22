"""生成课程数据集（确定性、字节可复现）。

课程不再把数据内联在正文里，而是引用 ``content/datasets/`` 下的 CSV
（设计见 ``docs/learning-workspace-redesign-2026-10-21.md`` §7）。

约定：

* 固定 ``SEED``，同一份代码重跑必须得到**字节一致**的产物；
* 只写 UTF-8 + LF，方便 docker（Linux）与本地（Windows）表现一致；
* 每个文件在 ``manifest.json`` 里记 sha256 / 字节数 / 行数，
  ``--check`` 用来在 CI 与本地校验"数据没被悄悄改过"；
* 单课数据集总量 ≤ 5MB（lint L6）。

用法::

    .venv/Scripts/python.exe scripts/build_datasets.py            # 重新生成
    .venv/Scripts/python.exe scripts/build_datasets.py --check    # 只校验，不写盘
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 20251021
ORDER_COUNT = 5000
CUSTOMER_COUNT = 800
PRODUCT_COUNT = 120
START_DATE = date(2025, 1, 1)
END_DATE = date(2025, 12, 31)
MAX_DATASET_BYTES = 5 * 1024 * 1024

DATASET_DIR = Path(__file__).resolve().parent.parent / "content" / "datasets" / "ecommerce"

REGIONS = ("华东", "华北", "华南", "西南")
CITIES = {
    "华东": ("上海", "杭州", "南京", "苏州", "合肥"),
    "华北": ("北京", "天津", "石家庄", "太原"),
    "华南": ("深圳", "广州", "东莞", "厦门"),
    "西南": ("成都", "重庆", "昆明", "贵阳"),
}
CHANNELS = ("app", "web", "mini_program", "offline")
SEGMENTS = ("新客", "活跃", "沉睡", "高价值")
CATEGORIES = ("数码", "家居", "服饰", "图书", "食品")
SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张"
GIVEN_NAMES = ("伟", "芳", "娜", "敏", "静", "磊", "洋", "勇", "艳", "杰", "涛", "明", "超", "秀兰", "晓东")

# 品类 -> (单价下界, 单价上界, 成本率)
CATEGORY_PRICE = {
    "数码": (199.0, 3999.0, 0.68),
    "家居": (39.0, 899.0, 0.55),
    "服饰": (59.0, 699.0, 0.42),
    "图书": (19.0, 129.0, 0.35),
    "食品": (9.0, 199.0, 0.60),
}
DISCOUNTS = (1.0, 1.0, 1.0, 0.9, 0.85, 0.8)

ORDERS_COLUMNS = (
    "order_id",
    "customer_id",
    "product_id",
    "region",
    "channel",
    "quantity",
    "unit_price",
    "discount",
    "amount",
    "order_date",
    "refunded",
)
CUSTOMERS_COLUMNS = ("customer_id", "name", "city", "region", "segment", "signup_date")
PRODUCTS_COLUMNS = ("product_id", "category", "unit_price", "cost", "launch_date")


def _money(value: float) -> str:
    return f"{value:.2f}"


def _ratio(value: float) -> str:
    return f"{value:.2f}"


def _random_date(rng: random.Random, lower: date, upper: date) -> date:
    span = (upper - lower).days
    return lower + timedelta(days=rng.randint(0, span))


def build_products(rng: random.Random) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(PRODUCT_COUNT):
        category = CATEGORIES[index % len(CATEGORIES)]
        low, high, cost_ratio = CATEGORY_PRICE[category]
        unit_price = round(rng.uniform(low, high), 2)
        rows.append(
            {
                "product_id": f"P{index + 1:04d}",
                "category": category,
                "unit_price": _money(unit_price),
                "cost": _money(round(unit_price * cost_ratio, 2)),
                "launch_date": _random_date(rng, date(2023, 1, 1), date(2025, 6, 30)).isoformat(),
            }
        )
    return rows


def build_customers(rng: random.Random) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(CUSTOMER_COUNT):
        region = rng.choice(REGIONS)
        name = rng.choice(SURNAMES) + rng.choice(GIVEN_NAMES)
        rows.append(
            {
                "customer_id": f"C{index + 1:05d}",
                "name": name,
                "city": rng.choice(CITIES[region]),
                "region": region,
                "segment": rng.choice(SEGMENTS),
                "signup_date": _random_date(rng, date(2023, 6, 1), date(2025, 12, 31)).isoformat(),
            }
        )
    return rows


def build_orders(
    rng: random.Random,
    products: list[dict[str, str]],
    customers: list[dict[str, str]],
) -> list[dict[str, str]]:
    price_by_product = {row["product_id"]: float(row["unit_price"]) for row in products}
    region_by_customer = {row["customer_id"]: row["region"] for row in customers}
    product_ids = list(price_by_product)
    customer_ids = list(region_by_customer)
    rows: list[dict[str, str]] = []
    for index in range(ORDER_COUNT):
        customer_id = rng.choice(customer_ids)
        product_id = rng.choice(product_ids)
        unit_price = price_by_product[product_id]
        quantity = rng.choices((1, 2, 3, 4, 5), weights=(55, 22, 12, 7, 4))[0]
        discount = rng.choice(DISCOUNTS)
        rows.append(
            {
                "order_id": f"O{index + 1:06d}",
                "customer_id": customer_id,
                "product_id": product_id,
                "region": region_by_customer[customer_id],
                "channel": rng.choice(CHANNELS),
                "quantity": str(quantity),
                "unit_price": _money(unit_price),
                "discount": _ratio(discount),
                "amount": _money(round(unit_price * quantity * discount, 2)),
                "order_date": _random_date(rng, START_DATE, END_DATE).isoformat(),
                "refunded": "true" if rng.random() < 0.04 else "false",
            }
        )
    return rows


def build_dirty_orders(rng: random.Random, orders: list[dict[str, str]]) -> list[dict[str, str]]:
    """从干净订单里造一张"脏表"，专门给数据清洗课用。

    故意注入的脏点（都可以被 Polars 处理掉，且不依赖随机时间）：

    - `discount` / `quantity` 片段缺失（空字符串 → 读进来是 null）
    - `amount` 部分行是 `N/A` 字符串（整列只能按 str 读）
    - `order_date` 部分行是 `2025/11/22` 斜杠格式
    - `region` 带前后空格、`channel` 大小写不一致
    - 整行重复（含重复的 `order_id`）
    """
    sample = orders[:1200]
    dirty: list[dict[str, str]] = []
    for index, row in enumerate(sample):
        item = dict(row)
        if index % 37 == 5:
            item["discount"] = ""
        if index % 53 == 7:
            item["quantity"] = ""
        if index % 41 == 11:
            item["amount"] = "N/A"
        if index % 29 == 3:
            item["order_date"] = item["order_date"].replace("-", "/")
        if index % 23 == 9:
            item["region"] = f" {item['region']} "
        if index % 31 == 13:
            item["channel"] = item["channel"].upper()
        dirty.append(item)
    # 整行重复：挑 30 行原样再追加一次（order_id 也跟着重复）
    for offset in range(0, 30):
        dirty.append(dict(sample[offset * 17 % len(sample)]))
    return dirty


def render_csv(rows: list[dict[str, str]], columns: tuple[str, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in columns})
    return buffer.getvalue().encode("utf-8")


def render_readme(counts: dict[str, int]) -> bytes:
    text = f"""# ecommerce 数据集

由 `scripts/build_datasets.py` 生成，**请勿手改**（`--check` 会失败）。固定 seed `{SEED}`，
重跑得到字节一致的文件。

| 文件 | 行数 | 说明 |
|---|---|---|
| `orders.csv` | {counts["orders"]} | 订单明细：一个订单一行 |
| `orders_dirty.csv` | {counts["dirty_orders"]} | 上面 1200 行 + 人为注入脏点，供数据清洗课练习 |
| `customers.csv` | {counts["customers"]} | 客户主数据：`region` 为所属大区 |
| `products.csv` | {counts["products"]} | 商品主数据：单价、成本、上架日期 |

`orders_dirty.csv` 故意注入的脏点（字段与 `orders.csv` 相同）：

| 脏点 | 形式 | 处理手段 |
|---|---|---|
| `discount` / `quantity` 缺失 | 空单元格 → null | `null_count()` / `fill_null()` |
| `amount` 出现 `N/A` | 整列被读成字符串 | `cast(pl.Float64, strict=False)` |
| `order_date` 混格式 | 部分 `2025/11/22` | `str.replace()` 后再 `str.to_date()` |
| `region` 前后空格、`channel` 大写 | `" 华东"` / `"APP"` | `str.strip_chars()` / `str.to_lowercase()` |
| 整行重复（含重复 `order_id`） | 追加 30 行 | `unique(subset=["order_id"])` |

`orders.csv` 字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `order_id` | str | `O000001` 形式，唯一 |
| `customer_id` | str | 关联 `customers.csv` |
| `product_id` | str | 关联 `products.csv` |
| `region` | str | 客户所属大区（华东/华北/华南/西南） |
| `channel` | str | app / web / mini_program / offline |
| `quantity` | int | 1-5 |
| `unit_price` | float | 商品单价快照（下单时点） |
| `discount` | float | 0.8 / 0.85 / 0.9 / 1.0 |
| `amount` | float | `round(unit_price * quantity * discount, 2)` |
| `order_date` | date | 2025-01-01 ~ 2025-12-31 |
| `refunded` | bool | `true` 表示已退款（约占 4%） |

已知的"数据脏点"（留给数据清洗课）：`customers.signup_date` 可能晚于客户的
第一笔订单；`orders.amount` 与 `unit_price * quantity * discount` 存在分位舍入差。
"""
    return text.encode("utf-8")


def build_all() -> dict[str, bytes]:
    rng = random.Random(SEED)
    products = build_products(rng)
    customers = build_customers(rng)
    orders = build_orders(rng, products, customers)
    dirty_orders = build_dirty_orders(random.Random(SEED + 1), orders)

    files = {
        "orders.csv": render_csv(orders, ORDERS_COLUMNS),
        "orders_dirty.csv": render_csv(dirty_orders, ORDERS_COLUMNS),
        "customers.csv": render_csv(customers, CUSTOMERS_COLUMNS),
        "products.csv": render_csv(products, PRODUCTS_COLUMNS),
        "README.md": render_readme(
            {
                "orders": len(orders),
                "dirty_orders": len(dirty_orders),
                "customers": len(customers),
                "products": len(products),
            }
        ),
    }
    files["manifest.json"] = render_manifest(files)
    return files


def render_manifest(files: dict[str, bytes]) -> bytes:
    entries = {}
    for name, payload in files.items():
        if name == "manifest.json":
            continue
        entries[name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "rows": _row_count(name, payload),
        }
    manifest = {"seed": SEED, "generator": "scripts/build_datasets.py", "files": entries}
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _row_count(name: str, payload: bytes) -> int:
    if not name.endswith(".csv"):
        return 0
    return max(payload.count(b"\n") - 1, 0)


def write_artifacts(
    target: Path,
    files: dict[str, bytes],
    *,
    check: bool = False,
) -> list[str]:
    """写入（或用 ``check=True`` 校验）产物，返回问题列表。"""
    problems: list[str] = []
    total = sum(len(payload) for payload in files.values())
    if total > MAX_DATASET_BYTES:
        problems.append(
            f"数据集总大小 {total} 字节超过上限 {MAX_DATASET_BYTES} 字节（lint L6）"
        )

    for name, payload in sorted(files.items()):
        if b"\r\n" in payload:
            problems.append(f"{name}: 出现 CRLF，数据集只允许 LF 换行")
        path = target / name
        if check:
            if not path.exists():
                problems.append(f"{name}: 文件缺失（跑一次不带 --check 的生成）")
                continue
            existing = path.read_bytes()
            if existing != payload:
                problems.append(
                    f"{name}: 与生成结果不一致"
                    f"（现有 {len(existing)} 字节 / 期望 {len(payload)} 字节，"
                    f"sha256 {hashlib.sha256(existing).hexdigest()[:12]} vs "
                    f"{hashlib.sha256(payload).hexdigest()[:12]}）"
                )
        else:
            target.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成课程数据集（确定性）")
    parser.add_argument(
        "--out",
        type=Path,
        default=DATASET_DIR,
        help=f"输出目录（默认 {DATASET_DIR}）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只校验现有文件是否与生成结果一致，不写盘",
    )
    args = parser.parse_args(argv)

    files = build_all()
    problems = write_artifacts(args.out, files, check=args.check)
    if problems:
        for problem in problems:
            print(f"[失败] {problem}", file=sys.stderr)
        return 1

    if args.check:
        print(f"数据集校验通过：{len(files) - 1} 个文件，seed {SEED}")
        return 0

    for name in sorted(files):
        payload = files[name]
        print(f"{name}: {len(payload)} 字节 sha256={hashlib.sha256(payload).hexdigest()[:16]}")
    print(f"已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())