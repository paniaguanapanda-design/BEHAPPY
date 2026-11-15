// Codigo de quien recomendo la app (embajador, cartel con QR, admin de grupo...).
// Llega en el link (?ref=codigo) o en la cookie bh_ref que deja be-happyapp.com, o se escribe a mano al registrarse.
// Se guarda el PRIMER codigo (primer contacto) y el servidor lo graba solo al crear la cuenta.
import { Platform } from "react-native";
import { storage } from "@/src/utils/storage";

const KEY = "referral_code";
const REF_RE = /^[a-z0-9][a-z0-9_-]{1,39}$/;

export function cleanRef(value: string | null | undefined): string | null {
  const ref = (value || "").trim().toLowerCase();
  return REF_RE.test(ref) ? ref : null;
}

function refFromWeb(): string | null {
  if (Platform.OS !== "web" || typeof window === "undefined") return null;
  try {
    const fromUrl = cleanRef(new URLSearchParams(window.location.search).get("ref"));
    if (fromUrl) return fromUrl;
    const m = document.cookie.match(/(?:^|;\s*)bh_ref=([^;]+)/);
    return m ? cleanRef(decodeURIComponent(m[1])) : null;
  } catch {
    return null;
  }
}

/** Llamar al abrir la app: guarda el codigo del link si todavia no hay uno. */
export async function captureReferral(): Promise<void> {
  const found = refFromWeb();
  if (!found) return;
  const current = await storage.getItem(KEY, null);
  if (!current) await storage.setItem(KEY, found);
}

export async function getReferral(): Promise<string | null> {
  const v = await storage.getItem(KEY, null);
  return typeof v === "string" ? cleanRef(v) : null;
}

/** El codigo escrito a mano en el registro manda sobre el del link. */
export async function setReferral(value: string): Promise<void> {
  const ref = cleanRef(value);
  if (ref) await storage.setItem(KEY, ref);
}
