/**
 * 生成 UUID v4 格式的随机 ID。
 *
 * crypto.randomUUID 仅在安全上下文（HTTPS / localhost）可用，
 * 明文 HTTP 部署时浏览器不暴露该函数，需降级为
 * crypto.getRandomValues 手工拼装（后者不受安全上下文限制）。
 */
export function randomId(): string {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID();
    }
    if (
        typeof crypto !== "undefined" &&
        typeof crypto.getRandomValues === "function"
    ) {
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        const view = new DataView(bytes.buffer);
        view.setUint8(6, (view.getUint8(6) & 0x0f) | 0x40); // version 4
        view.setUint8(8, (view.getUint8(8) & 0x3f) | 0x80); // variant 10xx
        const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    // 极端环境（无 Web Crypto）：时间戳 + 随机数，仅保证基本唯一性
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
