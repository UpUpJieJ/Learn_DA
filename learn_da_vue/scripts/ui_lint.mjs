#!/usr/bin/env node
// Semantic UI rules. Baselines store exact source/token occurrences, never net counts.
// --update-baseline may only remove existing allowances; shared UI has no allowances.
import { readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RULES = [
    { key: "palette", pattern: /\b(?:(?:blue|emerald|red|orange|indigo|green|amber|violet|purple|pink|teal|cyan|lime|rose|yellow|sky|fuchsia|gray|slate|zinc|neutral|stone)-\d{2,3}|(?:bg|text|border|ring|outline|fill|stroke|decoration|from|via|to|divide|placeholder|caret|accent|shadow)-(?:white|black))\b/g },
    { key: "radius", pattern: /\brounded(?:(?!-)\b|-(?!(?:card|control|pill|none)\b)[\w\[\].%-]+\b)/g },
    { key: "shadow", pattern: /\bshadow-(?!(?:card|pop|none)\b)[\w\[\].%-]+\b/g },
];
const normalize = (name) => name.replaceAll("\\", "/");
const isUi = (name) => normalize(name).startsWith("src/components/ui/");
const identity = (v) => JSON.stringify([normalize(v.file), v.rule, v.source, v.token]);

function walk(dir, out = []) {
    if (!existsSync(dir)) return out;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (["node_modules", "dist", "__tests__"].includes(entry.name)) continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full, out);
        else if (/\.(vue|ts|css)$/.test(entry.name) && !/\.(spec|test)\.[^.]+$/.test(entry.name)) out.push(full);
    }
    return out;
}
export function collect(root = ROOT) {
    const files = walk(path.join(root, "src"));
    if (existsSync(path.join(root, "index.html"))) files.push(path.join(root, "index.html"));
    const violations = [];
    for (const full of files) {
        const file = normalize(path.relative(root, full));
        readFileSync(full, "utf8").split(/\r?\n/).forEach((source, line) => {
            for (const rule of RULES) {
                rule.pattern.lastIndex = 0;
                for (const match of source.matchAll(rule.pattern)) {
                    violations.push({file, rule: rule.key, source: source.trim(), token: match[0], line: line + 1});
                }
            }
        });
    }
    return {fileCount: files.length, violations};
}
export function findNewViolations(actual, baseline) {
    const allowed = new Map();
    for (const item of baseline.violations ?? []) {
        const key = identity(item); allowed.set(key, (allowed.get(key) ?? 0) + 1);
    }
    return actual.filter(item => {
        const key = identity(item), count = allowed.get(key) ?? 0;
        if (isUi(item.file) || count === 0) return true;
        allowed.set(key, count - 1); return false;
    });
}
export function run(root = ROOT, {update = false, log = console.log} = {}) {
    const baselinePath = path.join(root, "scripts", "ui_lint.baseline.json");
    let baseline;
    try {
        baseline = existsSync(baselinePath) ? JSON.parse(readFileSync(baselinePath, "utf8")) : {version:2, violations:[]};
        if (!baseline || typeof baseline !== "object" || (baseline.violations !== undefined && !Array.isArray(baseline.violations))) throw new Error("invalid baseline");
    } catch (error) { log(`基线文件损坏：${error.message}`); return 2; }
    const {fileCount, violations} = collect(root);
    const additions = findNewViolations(violations, baseline);
    log(`ui_lint：扫描 ${fileCount} 个文件，${RULES.length} 条规则`);
    if (additions.length) {
        for (const item of additions) log(`  ${item.file}:${item.line} ${item.rule}: ${item.token}`);
        log(`新增违规 ${additions.length} 处；拒绝扩大基线。`); return 1;
    }
    if (update) {
        const payload = {version:2, note:"Exact existing occurrences only; shared UI is always zero tolerance.", violations:violations.filter(v => !isUi(v.file))};
        writeFileSync(baselinePath, `${JSON.stringify(payload,null,2)}\n`, "utf8");
        log(`已收紧基线：${payload.violations.length} 处。`);
    } else log("通过：没有新增视觉规范违规。");
    return 0;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    process.exitCode = run(ROOT, {update:process.argv.includes("--update-baseline")});
}
