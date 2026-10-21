#!/usr/bin/env node
// =====================================================
// ui_lint：把"视觉统一"变成可执行的检查
//
// 背景（learn_da/docs/learning-workspace-redesign-2026-10-21.md §15.1）：
//   main.css 里定义了主色 token，全站引用 0 次；实际用的是 blue-* 201 次、
//   emerald-* 100 次，圆角 5 档、阴影 5 档。这类问题靠 review 抓不住，只能靠脚本。
//
// 三条规则：
//   palette  raw palette（blue-500 / emerald-100 …）→ 用语义 token（brand/ok/warn/err/ink/surface/line）
//   radius   只许 rounded-card / rounded-control / rounded-pill / rounded-full / rounded-none
//   shadow   只许 shadow-card / shadow-pop / shadow-none
//
// 存量代码用基线文件（scripts/ui_lint.baseline.json）兜住：
//   - 实际数 > 基线 → 报错退出 1（新增违规，必须改）
//   - 实际数 < 基线 → 提示"可收紧"（移除代码后顺手跑 --update-baseline）
//   - src/components/ui/** 不参与基线：基础组件必须零违规
//
// 用法：
//   node scripts/ui_lint.mjs                 检查
//   node scripts/ui_lint.mjs --update-baseline  重写基线（仅在没有新增违规时使用）
// =====================================================

import { readFileSync, readdirSync, statSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "src");
const BASELINE_PATH = path.join(ROOT, "scripts", "ui_lint.baseline.json");
const UI_DIR = path.join("src", "components", "ui");
const UPDATE = process.argv.includes("--update-baseline");

const RULES = [
    {
        key: "palette",
        title: "raw palette",
        hint: "改用语义 token：brand-* / ok-* / warn-* / err-* / ink-* / surface-* / line",
        pattern:
            /\b(?:blue|emerald|red|orange|indigo|green|amber|violet|purple|pink|teal|cyan|lime|rose|yellow|sky|fuchsia)-\d{2,3}\b/g,
    },
    {
        key: "radius",
        title: "非标准圆角",
        hint: "只允许 rounded-card / rounded-control / rounded-pill",
        pattern: /\brounded-(?:sm|md|lg|xl|2xl|3xl)\b/g,
    },
    {
        key: "shadow",
        title: "非标准阴影",
        hint: "只允许 shadow-card / shadow-pop",
        pattern: /\bshadow-(?:sm|md|lg|xl|2xl|inner)\b/g,
    },
];

function walk(dir, out = []) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === "node_modules" || entry.name === "dist") continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            walk(full, out);
        } else if (/\.(vue|ts)$/.test(entry.name)) {
            out.push(full);
        }
    }
    return out;
}

function relPath(full) {
    return path.relative(ROOT, full).split(path.sep).join("/");
}

function collect() {
    const files = walk(SRC);
    const counts = {};
    const details = [];

    for (const full of files) {
        const rel = relPath(full);
        const text = readFileSync(full, "utf8");
        const lines = text.split(/\r?\n/);
        const perFile = {};

        for (const rule of RULES) {
            let total = 0;
            lines.forEach((line, index) => {
                rule.pattern.lastIndex = 0;
                const matches = line.match(rule.pattern);
                if (!matches) return;
                total += matches.length;
                details.push({ file: rel, line: index + 1, rule, text: line.trim().slice(0, 120) });
            });
            if (total > 0) perFile[rule.key] = total;
        }

        // src/components/ui/** 不写进基线：基础组件必须零违规
        if (!rel.startsWith(`${UI_DIR}/`)) {
            counts[rel] = perFile;
        }
    }

    return { fileCount: files.length, counts, details };
}

function loadBaseline() {
    if (!existsSync(BASELINE_PATH)) return { version: 1, counts: {} };
    try {
        const parsed = JSON.parse(readFileSync(BASELINE_PATH, "utf8"));
        return { version: 1, counts: parsed.counts ?? {} };
    } catch (error) {
        console.error(`基线文件损坏：${BASELINE_PATH}\n${error.message}`);
        process.exit(2);
    }
}

function writeBaseline(counts) {
    const compact = Object.fromEntries(
        Object.entries(counts).filter(([, perFile]) => Object.keys(perFile).length > 0),
    );
    const payload = {
        version: 1,
        note: "ui_lint 基线：存量违规数，只允许减少。改动后跑 node scripts/ui_lint.mjs --update-baseline 收紧。",
        counts: compact,
    };
    writeFileSync(BASELINE_PATH, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

function main() {
    const { fileCount, counts, details } = collect();

    if (UPDATE) {
        writeBaseline(counts);
        const total = Object.values(counts).reduce(
            (sum, perFile) => sum + Object.values(perFile).reduce((a, b) => a + b, 0),
            0,
        );
        console.log(`已写入基线 ${relPath(BASELINE_PATH)}：${Object.keys(counts).length} 个文件，${total} 处存量违规`);
        return;
    }

    const baseline = loadBaseline();
    const violations = [];
    const shrinkable = [];

    const touched = new Set([...Object.keys(counts), ...Object.keys(baseline.counts)]);
    for (const rel of touched) {
        const actual = counts[rel] ?? {};
        const base = baseline.counts[rel] ?? {};
        const isUiComponent = rel.startsWith(`${UI_DIR}/`);

        for (const rule of RULES) {
            const a = actual[rule.key] ?? 0;
            const b = isUiComponent ? 0 : (base[rule.key] ?? 0);
            if (a > b) violations.push({ file: rel, rule, actual: a, baseline: b });
            else if (a < b) shrinkable.push({ file: rel, rule, actual: a, baseline: b });
        }
    }

    console.log(`ui_lint：扫描 ${fileCount} 个文件，3 条规则`);

    if (shrinkable.length) {
        console.log(`\n可收紧 ${shrinkable.length} 处（实际少于基线，改完记得 --update-baseline）：`);
        for (const item of shrinkable.slice(0, 10)) {
            console.log(`  ${item.file}  ${item.rule.key} ${item.actual} < ${item.baseline}`);
        }
        if (shrinkable.length > 10) console.log(`  …还有 ${shrinkable.length - 10} 处`);
    }

    if (violations.length === 0) {
        console.log("通过：没有新增视觉规范违规。");
        return;
    }

    console.log(`\n新增违规 ${violations.length} 处：`);
    for (const item of violations) {
        const where = item.baseline > 0 ? `（基线 ${item.baseline}）` : "";
        console.log(`  ${item.file}: ${item.rule.title} ${item.actual} 处${where}`);
        console.log(`    → ${item.rule.hint}`);
        const hits = details.filter((d) => d.file === item.file && d.rule.key === item.rule.key).slice(-5);
        for (const hit of hits) console.log(`      ${item.file}:${hit.line}  ${hit.text}`);
    }
    console.log("\n修复后重跑：npm run lint:ui");
    process.exit(1);
}

main();