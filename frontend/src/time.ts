const LOCALE: Record<string, string> = { es: "es-ES", it: "it-IT" };

export const fmtDate = (iso: string, lang: string) =>
  new Date(iso).toLocaleDateString(LOCALE[lang] ?? "es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });

export function timeLabel(iso: string, lang: string) {
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay ? d.toLocaleTimeString(LOCALE[lang] ?? "es-ES", { hour: "2-digit", minute: "2-digit" }) : fmtDate(iso, lang);
}
