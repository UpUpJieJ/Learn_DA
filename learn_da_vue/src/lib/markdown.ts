/**
 * 公共 Markdown 渲染（纯文本 → HTML）
 *
 * 三处复用：LessonDetail / Playground / AgentPanel
 * 通过 MarkdownRenderOptions 控制差异化行为
 */

export interface MarkdownRenderOptions {
  /** 代码块是否可加载到 Playground（Playground 文档面板用） */
  codeLoadable?: boolean
  /** 代码块是否显示运行按钮（Agent 消息用） */
  codeRunnable?: boolean
  /** 单换行是否转为 <br>（聊天消息用） */
  newlineToBr?: boolean
}

export function renderMarkdown(
  md: string,
  options: MarkdownRenderOptions = {},
): string {
  if (!md) return ''

  const { codeLoadable = false, codeRunnable = false, newlineToBr = false } = options

  let html = md
    // ---- 代码块 ----
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang, code) => {
      const escaped = code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
      const langLabel = lang || 'text'

      // 通用代码块（LessonDetail）
      if (!codeLoadable && !codeRunnable) {
        const langClass = lang ? ` class="language-${lang}"` : ''
        return `<pre class="code-block" data-lang="${langLabel}"><code${langClass}>${escaped}</code></pre>`
      }

      // Playground 文档面板：带"加载代码"按钮
      if (codeLoadable) {
        return `<div class="doc-code-block" data-lang="${langLabel}"><div class="doc-code-header"><span>${langLabel}</span><button class="doc-code-load" data-code="${encodeURIComponent(code.trim())}">加载代码</button></div><pre><code>${escaped}</code></pre></div>`
      }

      // Agent 消息：带"复制"/"运行"按钮
      const id = `block-${Math.random().toString(36).slice(2, 7)}`
      return `<div class="code-block" data-id="${id}" data-lang="${langLabel}" data-code="${encodeURIComponent(code.trim())}"><div class="code-header"><span class="code-lang">${langLabel}</span><div class="code-actions"><button class="code-btn copy-btn" data-id="${id}">复制</button><button class="code-btn run-btn" data-id="${id}">运行</button></div></div><pre><code>${escaped}</code></pre></div>`
    })
    // ---- 行内代码 ----
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    // ---- 标题 h1-h4 ----
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // ---- 粗体 / 斜体 ----
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // ---- 无序列表 ----
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]*?<\/li>\n?)+/g, '<ul>$&</ul>')
    // ---- 有序列表 ----
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // ---- 水平线 ----
    .replace(/^---+$/gm, '<hr />')
    // ---- 引用块 ----
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    // ---- 链接 ----
    .replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>',
    )
    // ---- 段落（连续空行分段） ----
    .replace(/\n{2,}/g, '</p><p>')

  // 单换行转 <br>（聊天消息场景）
  if (newlineToBr) {
    html = html.replace(/\n/g, '<br />')
  }

  return `<p>${html}</p>`
}
