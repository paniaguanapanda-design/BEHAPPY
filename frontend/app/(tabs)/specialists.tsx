import React, { useEffect, useRef, useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api, imageUri } from "@/src/api";
import { CATEGORIES, tradesLabel, useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";
import { Button, Stars, VerifiedBadge } from "@/src/ui";

export default function Specialists() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { t, lang } = useI18n();
  const params = useLocalSearchParams<{ category?: string }>();
  const [cat, setCat] = useState<string>(params.category || "");
  const [search, setSearch] = useState("");
  const [qText, setQText] = useState("");
  const chipScroll = useRef<ScrollView>(null);
  const chipX = useRef<Record<string, number>>({});

  useEffect(() => {
    if (params.category) {
      setCat(params.category);
      const x = chipX.current[params.category];
      if (x != null) chipScroll.current?.scrollTo({ x: Math.max(0, x - 16), animated: true });
    }
  }, [params.category]);

  useEffect(() => {
    const h = setTimeout(() => setQText(search), 350);
    return () => clearTimeout(h);
  }, [search]);

  const q = useQuery({
    queryKey: ["specialists", cat, qText],
    queryFn: () => api<any[]>(`/specialists?category=${cat || "all"}${qText ? `&q=${encodeURIComponent(qText)}` : ""}`),
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>{t("specialists_title")}</Text>
        <View style={styles.search}>
          <Ionicons name="search" size={18} color={colors.muted} />
          <TextInput
            testID="specialist-search-input"
            style={styles.searchInput}
            placeholder={t("search_ph")}
            placeholderTextColor={colors.muted}
            value={search}
            onChangeText={setSearch}
          />
        </View>
      </View>
      <View style={styles.chipRow}>
        <ScrollView ref={chipScroll} horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
          {CATEGORIES.map((c) => (
            <Pressable
              key={c}
              testID={`category-chip-${c}`}
              onLayout={(e) => {
                chipX.current[c] = e.nativeEvent.layout.x;
                if (c === cat) chipScroll.current?.scrollTo({ x: Math.max(0, e.nativeEvent.layout.x - 16), animated: false });
              }}
              onPress={() => setCat(cat === c ? "" : c)}
              style={[styles.chip, cat === c && styles.chipOn]}
            >
              <Text style={[styles.chipText, cat === c && styles.chipTextOn]}>{t(`cat_${c}`)}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>
      <FlatList
        data={q.data || []}
        keyExtractor={(i) => i.specialist_id}
        contentContainerStyle={{ padding: 16, paddingBottom: bottomChrome + 24, gap: 12 }}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
        ListEmptyComponent={
          q.isLoading ? (
            <View style={{ gap: 12 }}>
              {[0, 1, 2].map((i) => (
                <View key={i} style={styles.skeleton} />
              ))}
            </View>
          ) : q.isError ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>{t("error_generic")}</Text>
              <Button title={t("retry")} onPress={() => q.refetch()} testID="specialists-retry-button" />
            </View>
          ) : (
            <View style={styles.empty} testID="no-specialists">
              <Ionicons name="construct-outline" size={40} color={colors.brandTertiary} />
              <Text style={styles.emptyText}>{t("no_specialists")}</Text>
            </View>
          )
        }
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeInDown.delay(index * 50).duration(350)}>
            <Pressable
              testID={`specialist-card-${item.specialist_id}`}
              onPress={() => router.push({ pathname: "/specialist/[id]", params: { id: item.specialist_id } })}
              style={({ pressed }) => [styles.card, pressed && { transform: [{ scale: 0.99 }], opacity: 0.95 }]}
            >
              <Image source={{ uri: imageUri(item.portfolio[0]?.image) }} style={styles.cover} contentFit="cover" />
              <View style={styles.cardBody}>
                <View style={styles.nameRow}>
                  <Text style={styles.name} numberOfLines={1}>
                    {item.name}
                  </Text>
                  {item.verified && <VerifiedBadge small />}
                </View>
                <Text style={styles.sub} numberOfLines={1}>
                  {tradesLabel(item.categories, t)} · {t("turin")}
                </Text>
                {item.rating_avg != null && (
                  <View style={styles.ratingRow} testID={`specialist-rating-${item.specialist_id}`}>
                    <Stars value={item.rating_avg} size={13} />
                    <Text style={styles.ratingText}>
                      {item.rating_avg.toFixed(1).replace(".", lang === "it" || lang === "es" ? "," : ".")} ({item.reviews_count})
                    </Text>
                  </View>
                )}
              </View>
            </Pressable>
          </Animated.View>
        )}
      />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 16, gap: 12, paddingBottom: 4 },
  title: { fontSize: 28, fontWeight: "800", color: c.onSurface, letterSpacing: -0.6, paddingHorizontal: 8 },
  search: { flexDirection: "row", alignItems: "center", gap: 8, height: 46, borderRadius: 12, backgroundColor: c.surfaceTertiary, paddingHorizontal: 14 },
  searchInput: { flex: 1, fontSize: 15, color: c.onSurface, height: 46 },
  chipRow: { height: 56, justifyContent: "center", borderBottomWidth: 1, borderBottomColor: c.divider },
  chipContent: { paddingHorizontal: 16, gap: 8, alignItems: "center" },
  chip: { height: 36, flexShrink: 0, paddingHorizontal: 14, borderRadius: 999, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, justifyContent: "center" },
  chipOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontSize: 14, fontWeight: "600", color: c.onSurfaceTertiary },
  chipTextOn: { color: c.onBrandPrimary },
  problemBanner: { flexDirection: "row", alignItems: "center", gap: 8, marginHorizontal: 16, marginTop: 12, padding: 12, borderRadius: 12, backgroundColor: c.brandSecondary },
  problemText: { flex: 1, color: c.onBrandSecondary, fontWeight: "600", fontSize: 13 },
  skeleton: { height: 180, borderRadius: 20, backgroundColor: c.surfaceTertiary },
  empty: { alignItems: "center", padding: 32, gap: 12 },
  emptyText: { color: c.muted, textAlign: "center", fontSize: 15 },
  card: { borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, overflow: "hidden" },
  cover: { width: "100%", height: 170, backgroundColor: c.surfaceTertiary },
  cardBody: { padding: 16, gap: 4 },
  cardTop: { flexDirection: "row", gap: 12, alignItems: "center" },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { fontSize: 17, fontWeight: "700", color: c.onSurface, flexShrink: 1 },
  sub: { fontSize: 13, color: c.muted },
  ratingRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  ratingText: { fontSize: 13, color: c.onSurfaceTertiary, fontWeight: "600" },
  thumbs: { flexDirection: "row", gap: 6 },
  thumb: { flex: 1, height: 84, borderRadius: 10 },
  stats: { flexDirection: "row", justifyContent: "space-between", borderTopWidth: 1, borderTopColor: c.divider, paddingTop: 12 },
  stat: { fontSize: 13, color: c.muted },
  statBold: { fontWeight: "800", color: c.onSurface },
}));
