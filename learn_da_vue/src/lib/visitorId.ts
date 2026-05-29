/**
 * 访客 ID 管理工具
 * 生成唯一标识符并持久化到 localStorage，用于关联用户的学习行为数据
 */

const STORAGE_KEY = "learn_da:visitor_id";

/**
 * 生成符合 UUID v4 格式的随机 ID
 */
function generateUUID(): string {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

/**
 * 获取当前访客 ID（首次访问时自动生成并持久化）
 */
export function getVisitorId(): string {
    let id = localStorage.getItem(STORAGE_KEY);
    if (!id) {
        id = generateUUID();
        localStorage.setItem(STORAGE_KEY, id);
    }
    return id;
}
