# ecommerce 数据集

由 `scripts/build_datasets.py` 生成，**请勿手改**（`--check` 会失败）。固定 seed `20251021`，
重跑得到字节一致的文件。

| 文件 | 行数 | 说明 |
|---|---|---|
| `orders.csv` | 5000 | 订单明细：一个订单一行 |
| `orders_dirty.csv` | 1230 | 上面 1200 行 + 人为注入脏点，供数据清洗课练习 |
| `customers.csv` | 800 | 客户主数据：`region` 为所属大区 |
| `products.csv` | 120 | 商品主数据：单价、成本、上架日期 |

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
