"""`python-collections` 的参考解（校验用，不进 API 响应）。"""

SOLUTIONS = {
    "c2": (
        "regions = ['华东', '华北', '华南', '西南']\n"
        "region_lines = 0\n"
        "for region in regions:\n"
        "    print(region)\n"
        "    region_lines = region_lines + 1\n"
        "print(region_lines)\n"
    ),
    "c3": (
        "amounts = [120, 899, 240, 59, 180, 620]\n"
        "total_amount = 0\n"
        "big_amounts = []\n"
        "for amount in amounts:\n"
        "    total_amount = total_amount + amount\n"
        "    if amount > 200:\n"
        "        big_amounts.append(amount)\n"
        "print(total_amount, big_amounts)\n"
    ),
    "c4": (
        "region_log = ['华东', '华南', '华东', '华北', '华东', '华南', '西南']\n"
        "region_counts = {}\n"
        "for region in region_log:\n"
        "    if region in region_counts:\n"
        "        region_counts[region] = region_counts[region] + 1\n"
        "    else:\n"
        "        region_counts[region] = 1\n"
        "print(region_counts)\n"
    ),
}