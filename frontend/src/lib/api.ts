const TOKEN_KEY = "assistant_token";

export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(`${BASE}${path}`, {
    method: options.method ?? (options.body ? "POST" : "GET"),
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (res.status === 401 && t) {
    token.clear();
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = `Lỗi ${res.status}`;
    try {
      const data = await res.json();
      msg = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map((d: { msg: string }) => d.msg).join(", ") : msg;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

/** Chuyển ISO từ server sang giá trị cho <input type="datetime-local"> theo giờ máy người dùng. */
export function toInputValue(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Giá trị datetime-local (giờ máy) -> ISO có múi giờ để gửi server. */
export function fromInputValue(v: string): string | null {
  return v ? new Date(v).toISOString() : null;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "Không có hạn";
  return new Date(iso).toLocaleString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}
