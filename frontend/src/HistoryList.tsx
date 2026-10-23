import React from "react";
import { FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { api, imageUri } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { localPhotos } from "@/src/localPhotos";
import { fmtDate } from "@/src/time";
import { makeStyles, useTheme } from "@/src/theme";

/** Profile > Historial: user's own scans only. Empty list renders nothing (no invented data). */
export function HistoryList({ bottom }: { bottom: number }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const { t, lang } = useI18n();
  const q = useQuery({ queryKey: ["diagnoses"], queryFn: () => api<any[]>("/diagnoses") });

  return (
    <FlatList
      testID="history-list"
      data={q.data || []}
      keyExtractor={(d) => d.diagnosis_id}
      contentContainerStyle={{ padding: 16, gap: 8, paddingBottom: bottom + 24 }}
      refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
      renderItem={({ item: d }) => {
        const photo = localPhotos[d.diagnosis_id] ?? imageUri(d.image_path);
        return (
          <Pressable
            testID={`history-item-${d.diagnosis_id}`}
            onPress={() => router.push({ pathname: "/diagnosis/[id]", params: { id: d.diagnosis_id } })}
            style={({ pressed }) => [styles.row, pressed && { opacity: 0.8 }]}
          >
            {photo ? <Image source={{ uri: photo }} style={styles.thumb} contentFit="cover" /> : <View style={styles.thumb} />}
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={styles.title} numberOfLines={1}>
                {d[`title_${lang}`] || d.title}
              </Text>
              <Text style={styles.sub} numberOfLines={1}>
                {t(`cat_${d.category}`)} · {fmtDate(d.created_at, lang)}
              </Text>
            </View>
          </Pressable>
        );
      }}
    />
  );
}

const useStyles = makeStyles((c) => ({
  row: { padding: 12, borderRadius: 12, backgroundColor: c.surfaceSecondary, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1, borderColor: c.border },
  thumb: { width: 56, height: 56, borderRadius: 10, backgroundColor: c.surfaceTertiary },
  title: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  sub: { fontSize: 13, color: c.muted },
}));
