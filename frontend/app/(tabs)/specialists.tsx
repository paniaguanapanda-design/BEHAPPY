import React, { useEffect, useRef, useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useMyPosition } from "@/src/position";
import { provinceLabel, saveMyProvince, useMyProvince } from "@/src/province";
import { ProvincePicker } from "@/src/ProvincePicker";
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
  // Toda Italia por provincias: solo salen especialistas de la provincia del cliente.
  const prov = useMyProvince();
  const province = prov.data?.province ?? null;
  const [changing, setChanging] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);
  const autoTried = useRef(false);
  // Primera vez con la ubicacion ya permitida: su provincia sale sola, sin preguntar.
  useEffect(() => {
    if (!prov.isSuccess || province || !pos || autoTried.current) return;
    autoTried.current = true;
    setAutoSaving(true);
    saveMyProvince(pos.lat, pos.lng)
      .catch(() => {})
      .finally(() => setAutoSaving(false));
  }, [prov.isSuccess, province, pos]);
  const showPicker = prov.isSuccess && (changing || (!province && !autoSaving));

  const q = useQuery({
    queryKey: ["specialists", cat, availOnly, province?.code, pos?.lat.toFixed(2), pos?.lng.toFixed(2)],
    enabled: me.ready && !!province,
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
        {province && !changing ? (
          <View style={styles.zone} testID="my-province">
            <View style={styles.zonePin}>
              <Ionicons name="location" size={14} color={colors.onBrandPrimary} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.zoneTitle} numberOfLines={1}>
                {provinceLabel(province, t)}
              </Text>
              <Text style={styles.zoneNote} numberOfLines={1}>
                {t("prov_only_yours")}
              </Text>
            </View>
            <Pressable testID="change-province" onPress={() => setChanging(true)} hitSlop={8} style={styles.zoneChange}>
              <Text style={styles.zoneChangeText}>{t("prov_change")}</Text>
            </Pressable>
          </View>
        ) : null}
      </View>
      {showPicker ? (
        <ScrollView contentContainerStyle={{ padding: 16, paddingTop: 4, paddingBottom: bottomChrome + 24 }} keyboardShouldPersistTaps="handled">
          <ProvincePicker onDone={() => setChanging(false)} onCancel={province ? () => setChanging(false) : undefined} />
        </ScrollView>
      ) : (
      <FlatList
        data={q.data || []}
        keyExtractor={(i) => i.specialist_id}
        contentContainerStyle={{ padding: 16, paddingTop: 4, paddingBottom: bottomChrome + 24, gap: 12 }}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
        ListEmptyComponent={
          q.isLoading || !me.ready || !province ? (
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
      )}
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
  zone: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: c.brandSecondary, borderWidth: 1.5, borderColor: "#FFD2B0", borderRadius: 14, paddingHorizontal: 12, paddingVertical: 8 },
  zonePin: { width: 26, height: 26, borderRadius: 13, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  zoneTitle: { fontSize: 15, fontWeight: "700", color: c.onSurface },
  zoneNote: { fontSize: 13, color: c.muted },
  zoneChange: { minHeight: 36, justifyContent: "center", paddingLeft: 4 },
  zoneChangeText: { fontSize: 14, fontWeight: "700", color: c.onBrandSecondary, textDecorationLine: "underline" },
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
