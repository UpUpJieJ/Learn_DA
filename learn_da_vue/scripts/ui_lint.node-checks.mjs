import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { collect, findNewViolations, run } from "./ui_lint.mjs";

function fixture(t, files) {
    const root = mkdtempSync(path.join(tmpdir(), "ui-lint-"));
    t.after(() => rmSync(root, {recursive:true, force:true}));
    for (const [name, text] of Object.entries(files)) {
        mkdirSync(path.dirname(path.join(root,name)), {recursive:true}); writeFileSync(path.join(root,name),text);
    }
    return root;
}
test("scans neutral/white/black, radius, CSS and index but excludes tests", t => {
    const root=fixture(t, {"src/A.vue":"text-slate-500 bg-white rounded-full", "src/a.css":"@apply text-black", "index.html":"bg-neutral-100", "src/__tests__/bad.ts":"bg-red-500", "src/A.spec.ts":"bg-red-500"});
    const result=collect(root);
    assert.equal(result.fileCount,3); assert.equal(result.violations.length,5);
});
test("shared UI violations are never whitelisted on either slash style", t => {
    const root=fixture(t,{"src/components/ui/A.vue":"shadow-sm"});
    const result=collect(root);
    const baseline={violations:result.violations.map(v=>({...v,file:v.file.replaceAll("/","\\")}))};
    assert.equal(findNewViolations(result.violations,baseline).length,1);
});
test("baseline cannot absorb a new violation or equal-count replacement", t => {
    const root=fixture(t,{"src/A.vue":"text-blue-500", "scripts/ui_lint.baseline.json":JSON.stringify({version:2,violations:[]})});
    const original=readFileSync(path.join(root,"scripts/ui_lint.baseline.json"),"utf8");
    assert.equal(run(root,{update:true,log:()=>{}}),1);
    assert.equal(readFileSync(path.join(root,"scripts/ui_lint.baseline.json"),"utf8"),original);
    const old=collect(root).violations;
    writeFileSync(path.join(root,"src/A.vue"),"text-red-500");
    assert.equal(findNewViolations(collect(root).violations,{violations:old}).length,1);
});

test("semantic tokens do not produce radius prefix false positives", t => {
    const root=fixture(t,{"src/A.vue":"rounded-card rounded-control rounded-pill rounded-none bg-editor-ink text-on-accent shadow-card shadow-pop"});
    assert.equal(collect(root).violations.length,0);
});
