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
    headers: { "Content-Type": "application/json", "X-BeHappy-Client": "app", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
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

export type ImageSrc = { uri: string; headers?: Record<string, string>; cacheKey?: string };

// The session token travels in the Authorization header, never inside the image address.
export function imageSource(p?: string | null): ImageSrc | undefined {
  if (!p) return undefined;
  if (/^(https?:|data:|file:|content:|blob:)/.test(p)) return { uri: p };
  return { uri: `${API}/files/${p}`, headers: token ? { Authorization: `Bearer ${token}` } : undefined, cacheKey: p };
}

export async function uploadImage(uri: string, mimeType?: string | null): Promise<string> {
  const res = await uploadForm(`${API}/upload`, {
    headers: { "X-BeHappy-Client": "app", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    files: { file: { uri, name: "photo.jpg", mimeType: mimeType ?? "image/jpeg" } },
  });
  if (!res.ok) throw new Error(`Upload failed (${res.status})`);
  return (await res.json()).path;
}

export async function uploadRequestPhoto(uri: string, mimeType?: string | null): Promise<string> {
  const headers: Record<string, string> = { "X-BeHappy-Client": "app" };
  if (token) headers.Authorization = "Bearer " + token;
  const res = await uploadForm(`${API}/requests/photos`, {
    headers,
    files: { file: { uri, name: "request-photo.jpg", mimeType: mimeType ?? "image/jpeg" } },
  });
  if (!res.ok) {
    let message = `Photo upload failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {}
    throw new Error(message);
  }
  return (await res.json()).path;
}
