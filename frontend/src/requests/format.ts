/** Tiempo transcurrido en texto corto ("hace 5 min", "hace 2 h"...), usando las claves de traduccion time_*. */
export function relativeTime(value: string, t: (key: string) => string) {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) return t("time_now");
  if (minutes < 60) return t("time_minutes_ago").replace("{n}", String(minutes));
  const hours = Math.floor(minutes / 60);
  return hours < 24
    ? t("time_hours_ago").replace("{n}", String(hours))
    : t("time_days_ago").replace("{n}", String(Math.floor(hours / 24)));
}

/** Precio en euros con el formato del idioma (it-IT o es-ES). */
export function formatPrice(value: number, lang: string) {
  return new Intl.NumberFormat(lang === "it" ? "it-IT" : "es-ES", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}
