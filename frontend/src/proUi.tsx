import React from "react";
import { Text, View } from "react-native";
import { useI18n } from "@/src/i18n";
import { makeStyles } from "@/src/theme";

// Small orange "NUOVO" tag next to a feature until the person opens it once.
export function NewBadge() {
  const styles = useStyles();
  const { t } = useI18n();
  return (
    <View style={styles.badge}>
      <Text style={styles.text}>{t("new_badge")}</Text>
    </View>
  );
}

export const fmtMinutes = (m: number) => (m < 60 ? `${m}m` : `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}`);

const DAY_NAMES: Record<string, string[]> = {
  it: ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
  es: ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
};
export const DAY_LETTERS: Record<string, string[]> = {
  it: ["L", "M", "M", "G", "V", "S", "D"],
  es: ["L", "M", "X", "J", "V", "S", "D"],
};

export function scheduleText(sch: { days: number[]; from: string; to: string }, lang: string) {
  const names = DAY_NAMES[lang] || DAY_NAMES.it;
  const days = [...sch.days].sort((a, b) => a - b);
  const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1);
  const consecutive = days.length > 2 && days.every((d, i) => i === 0 || d === days[i - 1] + 1);
  const d = consecutive
    ? `${cap(names[days[0] - 1])}–${cap(names[days[days.length - 1] - 1])}`
    : days.map((x) => cap(names[x - 1])).join(", ");
  const h = (v: string) => (v.endsWith(":00") ? String(parseInt(v, 10)) : v.replace(":", "."));
  return `${d} ${h(sch.from)}–${h(sch.to)}`;
}

const useStyles = makeStyles((c) => ({
  badge: { backgroundColor: c.brandPrimary, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  text: { color: c.onBrandPrimary, fontSize: 10, fontWeight: "800", letterSpacing: 0.3 },
}));
