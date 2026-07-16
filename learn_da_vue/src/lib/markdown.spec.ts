import { describe, it, expect } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  // ── XSS protection ──────────────────────────────────────

  it("does not render raw <script> tags", () => {
    const html = renderMarkdown("<script>alert(1)</script>");
    // html: false means markdown-it escapes it; DOMPurify strips it
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<script ");
  });

  it("does not render raw event handlers as HTML attributes", () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>');
    // With html:false, markdown-it escapes the tag, so no real onerror attr
    // DOMPurify further strips it. Just verify no actual <img onerror= attribute
    expect(html).not.toMatch(/<img[^>]*onerror\s*=/i);
  });

  it("does not render javascript: as an href attribute", () => {
    const html = renderMarkdown("[click](javascript:alert(1))");
    // markdown-it escapes or drops it; must NOT produce href="javascript:..."
    expect(html).not.toMatch(/href\s*=\s*["']?\s*javascript:/i);
  });

  it("does not render raw SVG with javascript links", () => {
    const html = renderMarkdown('<svg><a xlink:href="javascript:alert(1)">x</a></svg>');
    // html: false → all tags escaped; DOMPurify strips them
    expect(html).not.toMatch(/<svg/i);
    // No actual anchor element with javascript href is created
    expect(html).not.toMatch(/<a[^>]*href\s*=\s*["']?\s*javascript:/i);
  });

  // ── Code block buttons ──────────────────────────────────

  it("keeps agent code actions as data-only buttons", () => {
    const html = renderMarkdown("```python\nprint(1)\n```", {
      codeRunnable: true,
    });
    expect(html).toContain("code-btn");
    expect(html).toContain("run-btn");
    expect(html).toContain("data-code=");
    expect(html).not.toContain("onclick=");
  });

  it("generates loadable code blocks for Playground docs", () => {
    const html = renderMarkdown("```python\nprint('hi')\n```", {
      codeLoadable: true,
    });
    expect(html).toContain("doc-code-load");
    expect(html).toContain("data-code=");
  });

  it("renders plain code blocks without buttons by default", () => {
    const html = renderMarkdown("```python\nprint(1)\n```");
    expect(html).toContain("<pre");
    expect(html).toContain("<code");
    expect(html).not.toContain("code-btn");
    expect(html).not.toContain("doc-code-load");
  });

  // ── Inline formatting ───────────────────────────────────

  it("renders bold, italic, and inline code", () => {
    const html = renderMarkdown("**bold** and *italic* and `code`");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<em>italic</em>");
    expect(html).toContain("<code");
  });

  // ── Headings ─────────────────────────────────────────────

  it("renders headings h1-h4", () => {
    const html = renderMarkdown("# H1\n## H2\n### H3\n#### H4");
    expect(html).toContain("<h1>");
    expect(html).toContain("<h2>");
    expect(html).toContain("<h3>");
    expect(html).toContain("<h4>");
  });

  // ── Links ────────────────────────────────────────────────

  it("renders safe links with noopener", () => {
    const html = renderMarkdown("[example](https://example.com)");
    expect(html).toContain("https://example.com");
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("does not produce href for javascript links", () => {
    const html = renderMarkdown("[evil](javascript:void(0))");
    // markdown-it won't produce an <a href="javascript:..."> — it escapes or drops
    expect(html).not.toMatch(/href\s*=\s*["']?\s*javascript:/i);
  });

  // ── newlineToBr ─────────────────────────────────────────

  it("converts newlines to <br> when newlineToBr is true", () => {
    const html = renderMarkdown("line1\nline2", { newlineToBr: true });
    expect(html).toContain("<br");
  });

  // ── Empty input ─────────────────────────────────────────

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
    expect(renderMarkdown(undefined as unknown as string)).toBe("");
  });

  // ── Tables ──────────────────────────────────────────────

  it("renders markdown tables", () => {
    const md = "| A | B |\n|---|---|\n| 1 | 2 |";
    const html = renderMarkdown(md);
    expect(html).toContain("<table>");
    expect(html).toContain("<th>");
    expect(html).toContain("<td>");
  });
});
