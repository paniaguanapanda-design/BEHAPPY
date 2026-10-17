import { uploadForm } from "@/src/utils/upload";

export const API = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export const setToken = (t: string | null) => {
  token = t;
};
export const getToken = () => token;
export const setUnauthorizedHandler = (fn: (() => void) | null) => {
  onUnauthorized = fn;
};

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && token) onUnauthorized?.();
  if (!res.ok) {
    let msg: unknown;
    try {
      msg = (await res.json()).detail;
    } catch {}
    throw new Error(typeof msg === "string" ? msg : `Error ${res.status}`);
  }
  return res.json();
}

export function imageUri(p?: string | null): string | undefined {
  if (!p) return undefined;
  if (p.startsWith("http") || p.startsWith("data:")) return p;
  return `${API}/files/${p}?token=${encodeURIComponent(token ?? "")}`;
}

export async function uploadImage(uri: string, mimeType?: string | null): Promise<string> {
  const res = await uploadForm(`${API}/upload`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    files: { file: { uri, name: "photo.jpg", mimeType: mimeType ?? "image/jpeg" } },
  });
  if (!res.ok) throw new Error(`Upload failed (${res.status})`);
  return (await res.json()).path;
}
