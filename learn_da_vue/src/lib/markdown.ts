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

  // =========================================================
  // Step 1: 提取并保护代码块，避免后续正则破坏其内容
  // =========================================================
  const codeBlocks: string[] = []

  let html = md.replace(/```([^\n]*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    const escaped = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    const langLabel = (lang || 'text').trim()
    const idx = codeBlocks.length

    // 通用代码块（LessonDetail）
    if (!codeLoadable && !codeRunnable) {
      const langClass = langLabel !== 'text' ? ` class="language-${langLabel}"` : ''
      codeBlocks.push(
        `<pre class="code-block" data-lang="${langLabel}"><code${langClass}>${escaped}</code></pre>`,
      )
    } else if (codeLoadable) {
      // Playground 文档面板：带"加载代码"按钮
      codeBlocks.push(
        `<div class="doc-code-block" data-lang="${langLabel}"><div class="doc-code-header"><span>${langLabel}</span><button class="doc-code-load" data-code="${encodeURIComponent(code.trim())}">加载代码</button></div><pre><code>${escaped}</code></pre></div>`,
      )
    } else {
      // Agent 消息：带"复制"/"运行"按钮
      const id = `block-${Math.random().toString(36).slice(2, 7)}`
      codeBlocks.push(
        `<div class="code-block" data-id="${id}" data-lang="${langLabel}" data-code="${encodeURIComponent(code.trim())}"><div class="code-header"><span class="code-lang">${langLabel}</span><div class="code-actions"><button class="code-btn copy-btn" data-id="${id}">复制</button><button class="code-btn run-btn" data-id="${id}">运行</button></div></div><pre><code>${escaped}</code></pre></div>`,
      )
    }

    return `\x00CODEBLOCK_${idx}\x00`
  })

  // =========================================================
  // Step 2: 提取并保护表格（在行内代码和段落处理之前）
  // =========================================================
  const tables: string[] = []

  html = html.replace(
    /(?:^|\n)(\|.+\|\n)((?:\|[-:| ]+\|\n))((?:\|.+\|\n?)+)/gm,
    (_match, headerRow: string, separatorRow: string, bodyRows: string) => {
      const parseRow = (row: string) =>
        row
          .trim()
          .replace(/^\||\|$/g, '')
          .split('|')
          .map((cell) => cell.trim())

      const headers = parseRow(headerRow)
      const rows = bodyRows
        .trim()
        .split('\n')
        .filter((r) => r.trim())
        .map(parseRow)

      let tableHtml = '<table><thead><tr>'
      for (const h of headers) {
        tableHtml += `<th>${applyInlineFormatting(h)}</th>`
      }
      tableHtml += '</tr></thead><tbody>'
      for (const row of rows) {
        tableHtml += '<tr>'
        for (const cell of row) {
          tableHtml += `<td>${applyInlineFormatting(cell)}</td>`
        }
        tableHtml += '</tr>'
      }
      tableHtml += '</tbody></table>'

      const idx = tables.length
      tables.push(tableHtml)
      return `\n\x00TABLE_${idx}\x00\n`
    },
  )

  // =========================================================
  // Step 3: 行内格式化（标题、粗体、斜体、行内代码、列表、引用、链接）
  // =========================================================

  html = html
    // ---- 标题 h1-h4 ----
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // ---- 无序列表 ----
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    // ---- 有序列表 ----
    .replace(/^\d+\. (.+)$/gm, '<oli>$1</oli>')
    // ---- 水平线 ----
    .replace(/^---+$/gm, '<hr />')
    // ---- 引用块 ----
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    // ---- 链接 ----
    .replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>',
    )

  // ---- 分别包裹无序列表和有序列表 ----
  html = html.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, '<ul>$&</ul>')
  html = html.replace(/(<oli>[\s\S]*?<\/oli>\n?)+/g, (_match) => {
    return '<ol>' + _match.replace(/<\/?oli>/g, (tag) => tag.replace('oli', 'li')) + '</ol>'
  })

  // ---- 行内格式（标题内容、段落内的粗体/斜体/行内代码） ----
  html = applyInlineFormatting(html)

  // ---- 段落（连续空行分段） ----
  html = html.replace(/\n{2,}/g, '</p><p>')

  // ---- 单换行转 <br>（聊天消息场景） ----
  if (newlineToBr) {
    html = html.replace(/\n/g, '<br />')
  }

  // =========================================================
  // Step 4: 还原被保护的代码块和表格
  // =========================================================
  html = html.replace(/\x00CODEBLOCK_(\d+)\x00/g, (_, idx) => codeBlocks[parseInt(idx)] || '')
  html = html.replace(/\x00TABLE_(\d+)\x00/g, (_, idx) => tables[parseInt(idx)] || '')

  return `<p>${html}</p>`
}

/**
 * 行内格式化：粗体、斜体、行内代码
 * 单独抽离，因为表格单元格也需要用
 */
function applyInlineFormatting(text: string): string {
  return text
    // 行内代码（必须在粗体之前处理，避免 `` 内的 * 被误匹配）
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    // 粗体+斜体
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    // 粗体
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // 斜体
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}
