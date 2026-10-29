import React, { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { DAY_LETTERS, fmtMinutes } from "@/src/proUi";
import { markSeen } from "@/src/seen";

const RANGES = [
  { key: "7", label: "range_7" },
  { key: "30", label: "range_30" },
  { key: "all", label: "range_all" },
] as const;

// The specialist's numbers: profile visits, clients who wrote, how fast they answer, rating.
export default function ProStats() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, lang } = useI18n();
  const [range, setRange] = useState<string>("30");
  const q = useQuery({ queryKey: ["pro-stats", range], queryFn: () => api<any>(`/specialists/me/stats?days=${range}`) });
  const d = q.data;
  const max = Math.max(1, ...(d?.daily || []).map((x: any) => x.views));
  const letters = DAY_LETTERS[lang] || DAY_LETTERS.it;

  useEffect(() => {
    markSeen("pro_stats");
  }, []);

  return (
    <View style={styles.root}>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="stats-back" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("stats_title")}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.chips}>
          {RANGES.map((r) => (
            <Pressable key={r.key} testID={`stats-range-${r.key}`} onPress={() => setRange(r.key)} style={[styles.chip, range === r.key && styles.chipOn]}>
              <Text style={[styles.chipText, range === r.key && styles.chipTextOn]}>{t(r.label)}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.lbl}>{t("stats_views")}</Text>
          <View style={styles.bigRow}>
            <Text style={styles.big}>{d ? d.views : "–"}</Text>
            {d?.views_change_pct ? (
              <Text style={[styles.up, d.views_change_pct < 0 && { color: colors.error }]}>
                {d.views_change_pct > 0 ? "▲" : "▼"} {Math.abs(d.views_change_pct)}%
              </Text>
            ) : null}
          </View>
          <View style={styles.bars}>
            {(d?.daily || Array.from({ length: 7 }, () => ({ views: 0 }))).map((x: any, i: number) => (
              <View key={i} style={styles.barCol}>
                <View style={[styles.bar, { height: `${Math.max(4, (x.views / max) * 100)}%` }, i === 6 && styles.barToday]} />
              </View>
            ))}
          </View>
          <View style={styles.barLabels}>
            {(d?.daily || []).map((x: any, i: number) => (
              <Text key={i} style={styles.barLabel}>
                {letters[x.weekday - 1]}
              </Text>
            ))}
          </View>
        </View>

        <View style={styles.card}>
          <Kv label={t("stats_clients")} value={d ? String(d.clients) : "–"} />
          <Kv label={t("stats_within_1h")} value={d?.response_within_1h_pct != null ? `${d.response_within_1h_pct}%` : "–"} />
          <Kv label={t("stats_avg_response")} value={d?.response_avg_min != null ? fmtMinutes(d.response_avg_min).replace("m", " min") : "–"} />
          <Kv
            label={t("stats_rating")}
            value={d?.rating_avg != null ? `★ ${d.rating_avg.toFixed(1).replace(".", ",")} (${d.reviews_count})` : "–"}
            last
          />
        </View>

        <View style={styles.tip}>
          <Text style={styles.tipText}>💡 {t("stats_tip")}</Text>
        </View>
      </ScrollView>
    </View>
  );
}

function Kv({ label, value, last }: { label: string; value: string; last?: boolean }) {
  const styles = useStyles();
  return (
    <View style={[styles.kv, last && { borderBottomWidth: 0 }]}>
      <Text style={styles.kvLabel}>{label}</Text>
      <Text style={styles.kvVal}>{value}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  top: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 4 },
  back: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  body: { padding: 16, gap: 14, paddingBottom: 32 },
  chips: { flexDirection: "row", gap: 8 },
  chip: { paddingHorizontal: 14, height: 36, justifyContent: "center", borderRadius: 999, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  chipOn: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  chipText: { fontSize: 13, fontWeight: "600", color: c.onSurface },
  chipTextOn: { color: c.onSurfaceInverse },
  card: { backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 18, padding: 14 },
  lbl: { fontSize: 13, fontWeight: "700", color: c.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 0.4 },
  bigRow: { flexDirection: "row", alignItems: "baseline", gap: 8, marginTop: 4 },
  big: { fontSize: 30, fontFamily: fonts.display, color: c.onSurface },
  up: { color: "#16A34A", fontSize: 12, fontWeight: "700" },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: 8, height: 120, paddingTop: 10 },
  barCol: { flex: 1, height: "100%", justifyContent: "flex-end" },
  bar: { backgroundColor: "#FFD2B0", borderTopLeftRadius: 6, borderTopRightRadius: 6, borderBottomLeftRadius: 2, borderBottomRightRadius: 2 },
  barToday: { backgroundColor: c.brandPrimary },
  barLabels: { flexDirection: "row", gap: 8, marginTop: 4 },
  barLabel: { flex: 1, textAlign: "center", fontSize: 11, color: c.muted },
  kv: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: c.divider },
  kvLabel: { fontSize: 15, color: c.onSurface, flex: 1 },
  kvVal: { fontSize: 15, fontWeight: "700", color: c.onSurface },
  tip: { backgroundColor: c.brandSecondary, borderWidth: 1, borderColor: "#FFD2B0", borderRadius: 18, padding: 14 },
  tipText: { fontSize: 14, lineHeight: 20, color: c.onSurface },
}));
