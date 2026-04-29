import axios, {
    type AxiosInstance,
    type AxiosRequestConfig,
    type AxiosResponse,
} from "axios";

// =====================================================
// 通用 API 响应结构（与后端 StdResp 对齐）
// =====================================================

export interface ApiResponse<T = unknown> {
    code: number;
    msg: string;
    data: T;
}

// =====================================================
// Axios 实例创建
// =====================================================

const instance: AxiosInstance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
    timeout: 30000,
    headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
    },
});

// =====================================================
// 请求拦截器
// =====================================================

instance.interceptors.request.use(
    (config) => config,
    (error) => {
        console.error("[Request Error]", error);
        return Promise.reject(error);
    },
);

// =====================================================
// 响应拦截器
// =====================================================

instance.interceptors.response.use(
    (response: AxiosResponse<ApiResponse>) => {
        const { data } = response;

        // 后端业务错误（HTTP 200 但 code >= 400）
        if (data.code !== undefined && data.code >= 400) {
            const err = new ApiError(data.msg ?? "请求失败", data.code);
            console.error("[Business Error]", err);
            return Promise.reject(err);
        }

        return response;
    },
    (error) => {
        if (axios.isCancel(error)) {
            console.warn("[Request Cancelled]", error.message);
            return Promise.reject(new CancelledError(error.message));
        }

        const status = error.response?.status;
        // 尝试从后端返回的 JSON 中读取错误消息
        const backendMsg =
            error.response?.data?.msg ?? error.response?.data?.message;
        const message =
            backendMsg ??
            httpErrorMessage(status) ??
            error.message ??
            "网络异常，请稍后重试";
        const apiError = new ApiError(message, status ?? -1);

        console.error("[HTTP Error]", status, message);
        return Promise.reject(apiError);
    },
);

// =====================================================
// 自定义错误类
// =====================================================

export class ApiError extends Error {
    constructor(
        message: string,
        public readonly code: number,
    ) {
        super(message);
        this.name = "ApiError";
    }
}

export class CancelledError extends Error {
    constructor(message?: string) {
        super(message ?? "请求已取消");
        this.name = "CancelledError";
    }
}

// =====================================================
// HTTP 状态码中文映射
// =====================================================

function httpErrorMessage(status?: number): string | null {
    const map: Record<number, string> = {
        400: "请求参数错误",
        401: "未授权，请重新登录",
        403: "无权限访问",
        404: "资源不存在",
        408: "请求超时",
        422: "数据校验失败",
        429: "请求过于频繁，请稍后重试",
        500: "服务器内部错误",
        502: "网关错误",
        503: "服务暂时不可用",
        504: "网关超时",
    };
    return status ? (map[status] ?? null) : null;
}

// =====================================================
// 请求取消管理
// =====================================================

const pendingRequests = new Map<string, AbortController>();

function buildRequestKey(config: AxiosRequestConfig): string {
    const params = config.params
        ? JSON.stringify(
              Object.entries(config.params as Record<string, unknown>)
                  .filter(([, value]) => value !== undefined)
                  .sort(([a], [b]) => a.localeCompare(b)),
          )
        : "";
    return `${config.method?.toUpperCase()}::${config.url}::${params}`;
}

export function cancelRequest(key: string, reason = "主动取消") {
    const controller = pendingRequests.get(key);
    if (controller) {
        controller.abort(reason);
        pendingRequests.delete(key);
    }
}

export function cancelAllRequests(reason = "路由切换，取消所有请求") {
    pendingRequests.forEach((controller) => controller.abort(reason));
    pendingRequests.clear();
}

// =====================================================
// 封装请求方法
// =====================================================

export async function request<T = unknown>(
    config: AxiosRequestConfig,
): Promise<T> {
    const key = buildRequestKey(config);
    const controller = new AbortController();

    cancelRequest(key);
    pendingRequests.set(key, controller);

    try {
        const response = await instance.request<ApiResponse<T>>({
            ...config,
            signal: controller.signal,
        });
        return response.data.data as T;
    } finally {
        if (pendingRequests.get(key) === controller) {
            pendingRequests.delete(key);
        }
    }
}

export function get<T = unknown>(
    url: string,
    params?: Record<string, unknown>,
    config?: AxiosRequestConfig,
) {
    return request<T>({ method: "GET", url, params, ...config });
}

export function post<T = unknown>(
    url: string,
    data?: unknown,
    config?: AxiosRequestConfig,
) {
    return request<T>({ method: "POST", url, data, ...config });
}

export function put<T = unknown>(
    url: string,
    data?: unknown,
    config?: AxiosRequestConfig,
) {
    return request<T>({ method: "PUT", url, data, ...config });
}

export function del<T = unknown>(url: string, config?: AxiosRequestConfig) {
    return request<T>({ method: "DELETE", url, ...config });
}

export default instance;
