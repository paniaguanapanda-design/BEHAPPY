import React, { useEffect, useState } from "react";
import { Linking, Pressable, ScrollView, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { markSeen } from "@/src/seen";
import { enablePush, pushAllowed } from "@/src/push";

// Phone notifications: a client writes, or someone nearby diagnoses a problem of the specialist's trade.
export default function ProAlerts() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, lang } = useI18n();
  const toast = useToast();
  const q = useQuery({ queryKey: ["pro-settings", lang], queryFn: () => api<any>(`/specialists/me/settings?lang=${lang}`) });
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [cats, setCats] = useState<string[]>([]);
  const [phoneOk, setPhoneOk] = useState(true);

  useEffect(() => {
    markSeen("pro_alerts");
    pushAllowed().then(setPhoneOk);
  }, []);
  useEffect(() => {
    if (q.data && enabled === null) {
      setEnabled(q.data.alerts.enabled);
      setCats(q.data.alerts.categories);
    }
  }, [q.data, enabled]);

  const save = async (en: boolean, cs: string[]) => {
    setEnabled(en);
    setCats(cs);
    if (en) {
      const ok = await enablePush(lang);
      setPhoneOk(ok);
    }
    try {
      await api("/specialists/me/alerts", { method: "PUT", body: { enabled: en, categories: cs } });
      queryClient.invalidateQueries({ queryKey: ["pro-settings"] });
    } catch (e: any) {
      toast(e.message || t("error_generic"), "error");
    }
  };

  const all: string[] = q.data?.categories || [];

  return (
    <View style={styles.root}>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="alerts-back" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("alerts_title")}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <View style={[styles.card, styles.row]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>{t("alerts_switch")}</Text>
            <Text style={styles.note}>{t("alerts_switch_sub")}</Text>
          </View>
          <Switch
            testID="alerts-switch"
            value={!!enabled}
            onValueChange={(v) => save(v, cats.length ? cats : all)}
            trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
            thumbColor="#FFFFFF"
          />
        </View>

        {enabled ? (
          <>
            <Text style={styles.lbl}>{t("alerts_which")}</Text>
            <View style={styles.chips}>
              {all.map((c) => {
                const on = cats.includes(c);
                return (
                  <Pressable
                    key={c}
                    testID={`alerts-cat-${c}`}
                    onPress={() => save(true, on ? cats.filter((x) => x !== c) : [...cats, c])}
                    style={[styles.chip, on && styles.chipOn]}
                  >
                    <Text style={[styles.chipText, on && styles.chipTextOn]}>{t(`cat_${c}`)}</Text>
                  </Pressable>
                );
              })}
            </View>
          </>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.example}>{t("alerts_examples")}</Text>
          <Text style={styles.note}>• {t("alerts_ex_message")}</Text>
          <Text style={styles.note}>• {t("alerts_ex_nearby")}</Text>
        </View>

        {enabled && !phoneOk ? (
          <Pressable onPress={() => Linking.openSettings()} style={styles.warn} testID="alerts-open-settings">
            <Ionicons name="notifications-off-outline" size={18} color={colors.onBrandSecondary} />
            <Text style={styles.warnText}>{t("alerts_phone_off")}</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  top: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 4 },
  back: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  body: { padding: 16, gap: 14 },
  card: { backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 18, padding: 14, gap: 6 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  rowTitle: { fontSize: 15, fontWeight: "600", color: c.onSurface },
  note: { fontSize: 13, color: c.muted, lineHeight: 19 },
  lbl: { fontSize: 13, fontWeight: "700", color: c.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 0.4 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 14, height: 36, justifyContent: "center", borderRadius: 999, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  chipOn: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  chipText: { fontSize: 13, fontWeight: "600", color: c.onSurface },
  chipTextOn: { color: c.onSurfaceInverse },
  example: { fontSize: 14, fontWeight: "700", color: c.onSurface },
  warn: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: c.brandSecondary, borderRadius: 14, padding: 12 },
  warnText: { flex: 1, fontSize: 13, color: c.onBrandSecondary, fontWeight: "600" },
}));
