/**
 * 安全 Markdown 渲染（markdown-it + DOMPurify）
 *
 * 三处复用：LessonDetail / Playground / AgentPanel
 * 通过 MarkdownRenderOptions 控制差异化行为
 */

import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";

export interface MarkdownRenderOptions {
  /** 代码块是否可加载到 Playground（Playground 文档面板用） */
  codeLoadable?: boolean;
  /** 代码块是否显示运行按钮（Agent 消息用） */
  codeRunnable?: boolean;
  /** 单换行是否转为 <br>（聊天消息用） */
  newlineToBr?: boolean;
}

// ── Safe URL check ─────────────────────────────────────────

const SAFE_SCHEMES = /^(https?:|mailto:|\/|#)/i;

function isSafeUrl(href: string): boolean {
  const trimmed = href.trim();
  return SAFE_SCHEMES.test(trimmed) && !/^javascript:/i.test(trimmed);
}

// ── Custom fence renderer ─────────────────────────────────

function createFenceRenderer(options: MarkdownRenderOptions) {
  const { codeLoadable = false, codeRunnable = false } = options;

  return (tokens: any[], idx: number, _opts: any, _env: any, slf: any) => {
    const token = tokens[idx];
    const lang = (token.info || "text").trim();
    const code: string = token.content || "";
    const escaped = code
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    if (!codeLoadable && !codeRunnable) {
      const langClass =
        lang !== "text" ? ` class="language-${lang}"` : "";
      return `<pre class="code-block" data-lang="${lang}"><code${langClass}>${escaped}</code></pre>\n`;
    }

    if (codeLoadable) {
      return (
        `<div class="doc-code-block" data-lang="${lang}">` +
        `<div class="doc-code-header"><span>${lang}</span>` +
        `<button class="doc-code-load" data-code="${encodeURIComponent(code.trim())}">加载代码</button></div>` +
        `<pre><code>${escaped}</code></pre></div>\n`
      );
    }

    // codeRunnable — Agent messages
    const id = `block-${Math.random().toString(36).slice(2, 7)}`;
    return (
      `<div class="code-block" data-id="${id}" data-lang="${lang}" data-code="${encodeURIComponent(code.trim())}">` +
      `<div class="code-header"><span class="code-lang">${lang}</span>` +
      `<div class="code-actions">` +
      `<button class="code-btn copy-btn" data-id="${id}">复制</button>` +
      `<button class="code-btn run-btn" data-id="${id}">运行</button>` +
      `</div></div><pre><code>${escaped}</code></pre></div>\n`
    );
  };
}

// ── DOMPurify config ──────────────────────────────────────

const ALLOWED_TAGS = [
  "h1", "h2", "h3", "h4", "h5", "h6",
  "p", "br", "hr",
  "strong", "em", "del",
  "ul", "ol", "li",
  "blockquote", "pre", "code",
  "table", "thead", "tbody", "tr", "th", "td",
  "a", "div", "span", "button",
];

const ALLOWED_ATTR = [
  "class", "id",
  "data-id", "data-lang", "data-code",
  "href", "target", "rel",
];

// ── Main render function ──────────────────────────────────

export function renderMarkdown(
  md: string,
  options: MarkdownRenderOptions = {},
): string {
  if (!md) return "";

  const { newlineToBr = false } = options;

  const mdi = new MarkdownIt({
    html: false,
    linkify: false,
    breaks: newlineToBr,
  });

  // Override fence renderer
  mdi.renderer.rules.fence = createFenceRenderer(options);

  // Override link rendering to enforce safe URLs + noopener
  const defaultLinkOpen =
    mdi.renderer.rules.link_open ||
    ((tokens: any[], idx: number, opts: any, _env: any, slf: any) =>
      slf.renderToken(tokens, idx, opts));

  mdi.renderer.rules.link_open = (
    tokens: any[],
    idx: number,
    opts: any,
    env: any,
    slf: any,
  ) => {
    const token = tokens[idx];
    const hrefIdx = token.attrIndex("href");
    if (hrefIdx >= 0) {
      const href = token.attrs[hrefIdx][1];
      if (!isSafeUrl(href)) {
        // Replace unsafe href with empty
        token.attrs[hrefIdx][1] = "";
      }
    }
    // Add target and rel
    token.attrSet("target", "_blank");
    token.attrSet("rel", "noopener noreferrer");
    return defaultLinkOpen(tokens, idx, opts, env, slf);
  };

  let html = mdi.render(md);

  // Sanitize with DOMPurify
  html = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
  });

  return html;
}
