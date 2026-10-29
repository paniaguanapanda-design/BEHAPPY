import React, { useEffect, useState } from "react";
import { FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useMyPosition } from "@/src/position";
import { CATEGORIES, tradesLabel, useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { Avatar, Button } from "@/src/ui";

export default function Specialists() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { t, lang } = useI18n();
  const params = useLocalSearchParams<{ category?: string; diag?: string }>();
  const [cat, setCat] = useState<string>(params.category || "");
  const [availOnly, setAvailOnly] = useState(false);
  const me = useMyPosition();

  useEffect(() => {
    if (params.category) setCat(params.category);
  }, [params.category]);

  const pos = me.pos;
  const q = useQuery({
    queryKey: ["specialists", cat, availOnly, pos?.lat.toFixed(2), pos?.lng.toFixed(2)],
    enabled: me.ready,
    queryFn: () =>
      api<any[]>(
        `/specialists?category=${cat || "all"}${availOnly ? "&available=true" : ""}${pos ? `&lat=${pos.lat}&lng=${pos.lng}` : ""}`,
      ),
  });

  const subLine = (item: any) => {
    const parts: string[] = [];
    if (!cat) parts.push(tradesLabel(item.categories, t));
    if (item.rating_avg != null) parts.push(`★ ${item.rating_avg.toFixed(1).replace(".", ",")} (${item.reviews_count})`);
    if (item.distance_km != null) parts.push(t("km_away").replace("{n}", String(Math.max(1, Math.round(item.distance_km)))));
    if (item.response_min != null && item.available_now) parts.push(t("replies_in").replace("{n}", String(Math.max(1, item.response_min))));
    else if (item.available_now) parts.push(t("available_now").toLowerCase());
    else if (item.urgent) parts.push(t("accepts_urgent"));
    else if (item[`schedule_label_${lang}`]) parts.push(item[`schedule_label_${lang}`]);
    else if (!item.membership_active) parts.push(t("may_reply_later").toLowerCase());
    return parts.join(" · ");
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>{t("specialists_title")}</Text>
        <View style={styles.chips}>
          {CATEGORIES.map((c) => (
            <Pressable key={c} testID={`category-chip-${c}`} onPress={() => setCat(cat === c ? "" : c)} style={[styles.chip, cat === c && styles.chipOn]}>
              <Text style={[styles.chipText, cat === c && styles.chipTextOn]}>{t(`cat_${c}`)}</Text>
            </Pressable>
          ))}
          <Pressable testID="available-chip" onPress={() => setAvailOnly(!availOnly)} style={[styles.chip, styles.chipRow, availOnly && styles.chipOn]}>
            <View style={[styles.dot, availOnly && { backgroundColor: colors.onSurfaceInverse }]} />
            <Text style={[styles.chipText, availOnly && styles.chipTextOn]}>{t("available_now_plural")}</Text>
          </Pressable>
        </View>
        {pos ? (
          <Text style={styles.zoneNote}>{t("only_your_zone")}</Text>
        ) : me.ready && me.canAsk ? (
          <Pressable testID="ask-location" onPress={() => me.request()} style={styles.locBtn} hitSlop={6}>
            <Ionicons name="location-outline" size={16} color={colors.brandTertiary} />
            <Text style={styles.locText}>{t("enable_location_zone")}</Text>
          </Pressable>
        ) : null}
      </View>
      <FlatList
        data={q.data || []}
        keyExtractor={(i) => i.specialist_id}
        contentContainerStyle={{ padding: 16, paddingTop: 4, paddingBottom: bottomChrome + 24, gap: 12 }}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
        ListEmptyComponent={
          q.isLoading || !me.ready ? (
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
              <Text style={styles.emptyText}>{availOnly ? t("no_specialists_now") : t("no_specialists")}</Text>
            </View>
          )
        }
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeInDown.delay(Math.min(index, 6) * 40).duration(250)}>
            <Pressable
              testID={`specialist-card-${item.specialist_id}`}
              onPress={() =>
                router.push({ pathname: "/specialist/[id]", params: params.diag ? { id: item.specialist_id, diag: params.diag } : { id: item.specialist_id } })
              }
              style={({ pressed }) => [styles.card, item.featured && styles.cardFeatured, pressed && { transform: [{ scale: 0.99 }] }]}
            >
              {item.featured ? (
                <View style={styles.badge} testID={`specialist-featured-${item.specialist_id}`}>
                  <Text style={styles.badgeText}>⭐ {t("featured_label")}</Text>
                </View>
              ) : null}
              <View style={styles.cardTop}>
                <Avatar uri={item.avatar} name={item.name} size={52} />
                <View style={{ flex: 1, gap: 2 }}>
                  <View style={styles.nameRow}>
                    <Text style={styles.name} numberOfLines={1}>
                      {item.name}
                    </Text>
                    {item.verified ? (
                      <View style={styles.ok}>
                        <Text style={styles.okText}>✔ {t("verified_short")}</Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={styles.sub} testID={`specialist-sub-${item.specialist_id}`}>
                    {subLine(item)}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.muted} />
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
  header: { paddingHorizontal: 16, gap: 12, paddingBottom: 10 },
  title: { fontSize: 28, fontFamily: fonts.display, color: c.onSurface, letterSpacing: -0.6 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { height: 36, paddingHorizontal: 12, borderRadius: 999, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, justifyContent: "center" },
  chipRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  chipOn: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  chipText: { fontSize: 13, fontWeight: "600", color: c.onSurface },
  chipTextOn: { color: c.onSurfaceInverse },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: c.onSurface },
  zoneNote: { fontSize: 13, color: c.muted },
  locBtn: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", minHeight: 32 },
  locText: { fontSize: 13, color: c.brandTertiary, fontWeight: "600" },
  skeleton: { height: 84, borderRadius: 18, backgroundColor: c.surfaceTertiary },
  empty: { alignItems: "center", padding: 32, gap: 12 },
  emptyText: { color: c.muted, textAlign: "center", fontSize: 15 },
  card: { borderRadius: 18, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, padding: 14, gap: 6 },
  cardFeatured: { borderWidth: 2, borderColor: c.brandPrimary, backgroundColor: "#FFFAF5" },
  badge: { alignSelf: "flex-start", backgroundColor: c.brandPrimary, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { fontSize: 11, fontWeight: "800", color: c.onBrandPrimary },
  cardTop: { flexDirection: "row", gap: 12, alignItems: "center" },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { fontSize: 16, fontFamily: fonts.display, color: c.onSurface, flexShrink: 1 },
  ok: { backgroundColor: "#E7F6EC", borderRadius: 999, paddingHorizontal: 7, paddingVertical: 2 },
  okText: { fontSize: 11, fontWeight: "700", color: "#16794A" },
  sub: { fontSize: 13, color: c.muted, lineHeight: 18 },
}));
