import React from "react";
import { Linking, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Stack, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";
import type { Announcement } from "@/src/AnnouncementPopup";

// Lista de novedades, promociones, eventos y sorteos activos (los ya vistos tambien aparecen).
export default function Novedades() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t } = useI18n();
  const list = useQuery({ queryKey: ["announcements-list"], queryFn: () => api<{ items: Announcement[] }>("/announcements") });
  const items = list.data?.items ?? [];

  return (
    <View style={[styles.screen, { paddingTop: insets.top + 12 }]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="news-back" accessibilityRole="button" accessibilityLabel={t("back")}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.heading}>{t("news_title")}</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: insets.bottom + 24 }}>
        {items.length === 0 ? (
          <Text style={styles.empty}>{t("news_empty")}</Text>
        ) : (
          items.map((a) => (
            <Pressable key={a.announcement_id} testID={`news-item-${a.announcement_id}`} onPress={() => a.link && Linking.openURL(a.link)} style={styles.card}>
              <Text style={styles.kind}>{t(`announce_${a.type}`)}</Text>
              <Text style={styles.title}>{a.title}</Text>
              <Text style={styles.text}>{a.text}</Text>
              {a.link ? <Text style={styles.more}>{t("announce_more")} ›</Text> : null}
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingBottom: 8 },
  heading: { color: c.onSurface, fontWeight: "800", fontSize: 22 },
  empty: { color: c.onSurfaceSecondary, fontSize: 15, textAlign: "center", marginTop: 40 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 18, padding: 16, gap: 6 },
  kind: { color: c.brandPrimary, fontWeight: "800", fontSize: 12, textTransform: "uppercase" },
  title: { color: c.onSurface, fontWeight: "800", fontSize: 17 },
  text: { color: c.onSurfaceSecondary, fontSize: 14, lineHeight: 20 },
  more: { color: c.brandPrimary, fontWeight: "800", marginTop: 4 },
}));
