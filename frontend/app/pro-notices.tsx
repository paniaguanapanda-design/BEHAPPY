import React, { useEffect } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { fmtDate } from "@/src/time";

// Avisos que el equipo de BE HAPPY te ha enviado. Solo se leen: aqui no se responde.
export default function ProNotices() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, lang } = useI18n();
  const q = useQuery({ queryKey: ["pro-notices"], queryFn: () => api<any>("/specialists/me/notices") });

  // Al abrir la pantalla quedan leidos (el contador de Perfil se pone a cero).
  useEffect(() => {
    api("/specialists/me/notices/read", { method: "POST" })
      .then(() => queryClient.invalidateQueries({ queryKey: ["pro-notices"] }))
      .catch(() => {});
  }, []);

  const items: any[] = q.data?.items || [];

  return (
    <View style={styles.root}>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="notices-back" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("notices_title")}</Text>
      </View>
      <ScrollView contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 24 }]}>
        <Text style={styles.note}>{t("notices_note")}</Text>
        {q.data && !items.length ? <Text style={styles.note}>{t("notices_empty")}</Text> : null}
        {items.map((n) => (
          <View key={n.notice_id} testID={`notice-${n.notice_id}`} style={styles.card}>
            <Text style={styles.date}>{fmtDate(n.created_at, lang)}</Text>
            <Text style={styles.subject}>{n.subject}</Text>
            <Text style={styles.text}>{n.text}</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  top: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 4 },
  back: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  body: { padding: 16, gap: 12 },
  note: { fontSize: 14, color: c.muted, lineHeight: 20 },
  card: { backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 14, padding: 14, gap: 6 },
  date: { fontSize: 12, color: c.muted },
  subject: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  text: { fontSize: 15, color: c.onSurface, lineHeight: 22 },
}));
