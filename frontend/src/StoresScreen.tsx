import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FlatList, Linking, Platform, Pressable, ScrollView, Share, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import * as Location from "expo-location";
import Constants from "expo-constants";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { API, api } from "@/src/api";
import { CATEGORIES, useI18n } from "@/src/i18n";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { Button, Loading } from "@/src/ui";
import { ReportSheet, STORE_REASONS } from "@/src/ReportSheet";

// react-native-maps is native only (the app ships on Android); on web the screen shows the list alone.
// Without a Google Maps key in the build the native map would crash on Android, so the list is shown alone.
const HAS_MAPS_KEY = Boolean(Constants.expoConfig?.extra?.hasMapsKey);
const Maps: typeof import("react-native-maps") | null =
  // The native map is not evaluated in web builds.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  Platform.OS === "web" || !HAS_MAPS_KEY ? null : require("react-native-maps");

type Store = {
  store_id: string;
  name: string;
  address: string;
  cap: string;
  city: string;
  phone: string;
  whatsapp: string;
  hours: string;
  categories: string[];
  lat: number;
  lng: number;
  distance_km?: number;
  photo_url: string | null;
};

type Pos = { lat: number; lng: number };

const RADIUS_KM = 15;

// Hardware stores near the user: its own tab (browse freely) and the screen opened from a diagnosis.
export function StoresScreen({ asTab = false }: { asTab?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t } = useI18n();
  const params = useLocalSearchParams<{ category?: string }>();
  const fromParams = (CATEGORIES as readonly string[]).includes(params.category ?? "") ? params.category : undefined;
  const [category, setCategory] = useState<string | undefined>(fromParams);
  const [perm, requestPerm] = Location.useForegroundPermissions();
  const [pos, setPos] = useState<Pos | null>(null);
  const [locError, setLocError] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const listRef = useRef<FlatList<Store>>(null);

  useEffect(() => {
    if (!perm?.granted || pos) return;
    let cancelled = false;
    (async () => {
      try {
        const last = await Location.getLastKnownPositionAsync();
        if (last && !cancelled) setPos({ lat: last.coords.latitude, lng: last.coords.longitude });
        const now = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        if (!cancelled) setPos({ lat: now.coords.latitude, lng: now.coords.longitude });
      } catch {
        if (!cancelled) setLocError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [perm?.granted, pos]);

  const q = useQuery({
    queryKey: ["stores", pos?.lat.toFixed(3), pos?.lng.toFixed(3), category],
    enabled: !!pos,
    queryFn: () =>
      api<Store[]>(`/stores/nearby?lat=${pos!.lat}&lng=${pos!.lng}&radius_km=${RADIUS_KM}${category ? `&category=${category}` : ""}`),
  });
  const stores = useMemo(() => q.data ?? [], [q.data]);

  const select = useCallback(
    (id: string) => {
      setSelected(id);
      const index = stores.findIndex((s) => s.store_id === id);
      if (index >= 0) listRef.current?.scrollToIndex({ index, animated: true, viewPosition: 0 });
    },
    [stores],
  );

  const header = (
    <View style={[styles.header, { paddingTop: insets.top + 8 }, asTab && { paddingHorizontal: 16 }]}>
      {asTab ? null : (
        <Pressable testID="stores-back-button" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
      )}
      <Text style={styles.title}>{t("stores_title")}</Text>
    </View>
  );

  if (!perm) return <Loading />;

  if (!perm.granted) {
    const blocked = !perm.canAskAgain;
    return (
      <View style={styles.root}>
        {header}
        <View style={styles.center}>
          <View style={styles.permIcon}>
            <Ionicons name="location" size={36} color={colors.onBrandPrimary} />
          </View>
          <Text style={styles.centerTitle}>{t("stores_loc_title")}</Text>
          <Text style={styles.centerText}>{t("stores_loc_text")}</Text>
          {blocked ? (
            <Button testID="stores-open-settings" title={t("open_settings")} icon="settings-outline" onPress={() => Linking.openSettings()} />
          ) : (
            <Button testID="stores-allow-location" title={t("stores_allow")} icon="location-outline" onPress={requestPerm} />
          )}
        </View>
      </View>
    );
  }

  if (!pos && !locError) return <Loading />;

  const empty = (
    <View style={styles.center} testID="stores-empty">
      <Ionicons name="storefront-outline" size={40} color={colors.muted} />
      {q.isError || locError ? (
        <>
          <Text style={styles.centerText}>{t("stores_error")}</Text>
          <Button title={t("retry")} onPress={() => (locError ? (setLocError(false), setPos(null)) : q.refetch())} />
        </>
      ) : (
        <>
          <Text style={styles.centerTitle}>{t("stores_empty")}</Text>
          <Text style={styles.centerText}>{t("stores_empty_sub")}</Text>
          <Button variant="secondary" icon="share-social-outline" title={t("stores_share")} onPress={() => Share.share({ message: t("stores_share_text") })} />
        </>
      )}
    </View>
  );

  // What the person needs: highlights the stores that sell it (shown first, then by distance).
  const chips = (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} style={styles.chipsBar}>
      {[undefined, ...CATEGORIES].map((c) => {
        const on = category === c;
        return (
          <Pressable
            key={c ?? "all"}
            testID={`stores-chip-${c ?? "all"}`}
            onPress={() => setCategory(c)}
            style={[styles.chip, on && styles.chipOn]}
          >
            <Text style={[styles.chipText, on && styles.chipTextOn]}>{c ? t(`cat_${c}`) : t("all")}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );

  return (
    <View style={styles.root}>
      {header}
      {chips}
      {Maps && pos ? (
        <Maps.default
          style={styles.map}
          provider={Platform.OS === "android" ? Maps.PROVIDER_GOOGLE : undefined}
          showsUserLocation
          initialRegion={{ latitude: pos.lat, longitude: pos.lng, latitudeDelta: 0.06, longitudeDelta: 0.06 }}
          testID="stores-map"
        >
          {stores.map((s) => (
            <Maps.Marker
              key={s.store_id}
              coordinate={{ latitude: s.lat, longitude: s.lng }}
              title={s.name}
              pinColor={selected === s.store_id ? colors.brandTertiary : colors.brandPrimary}
              onPress={() => select(s.store_id)}
            />
          ))}
        </Maps.default>
      ) : null}
      {q.isLoading ? (
        <Loading />
      ) : (
        <FlatList
          ref={listRef}
          data={stores}
          keyExtractor={(s) => s.store_id}
          contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: insets.bottom + 24, flexGrow: 1 }}
          ListEmptyComponent={empty}
          onScrollToIndexFailed={() => {}}
          renderItem={({ item: s }) => (
            <StoreCard
              store={s}
              active={selected === s.store_id}
              matches={!!category && s.categories.includes(category)}
              onReport={() => setReport(s.store_id)}
            />
          )}
        />
      )}
      <ReportSheet visible={!!report} onClose={() => setReport(null)} targetType="store" targetId={report ?? ""} reasons={STORE_REASONS} />
    </View>
  );
}

function StoreCard({ store: s, active, matches, onReport }: { store: Store; active: boolean; matches: boolean; onReport: () => void }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const wa = (s.whatsapp || "").replace(/[^0-9]/g, "");
  const directions = () =>
    Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lng}&travelmode=walking`);

  return (
    <View style={[styles.card, active && styles.cardActive]} testID={`store-${s.store_id}`}>
      <View style={styles.cardTop}>
        {s.photo_url ? (
          <Image source={{ uri: `${API.replace(/\/api$/, "")}${s.photo_url}` }} style={styles.photo} contentFit="cover" />
        ) : (
          <View style={[styles.photo, styles.photoEmpty]}>
            <Ionicons name="storefront" size={26} color={colors.brandPrimary} />
          </View>
        )}
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={styles.name} numberOfLines={2}>
            {s.name}
          </Text>
          <Text style={styles.address} numberOfLines={2}>
            {`${s.address}, ${s.city}`}
          </Text>
          {s.distance_km != null ? <Text style={styles.distance}>{`${s.distance_km.toLocaleString(undefined, { maximumFractionDigits: 1 })} km`}</Text> : null}
        </View>
        <Pressable testID={`store-report-${s.store_id}`} onPress={onReport} hitSlop={10} accessibilityLabel={t("stores_report")} style={styles.flag}>
          <Ionicons name="flag-outline" size={18} color={colors.muted} />
        </Pressable>
      </View>
      {matches ? (
        <View style={styles.match}>
          <Ionicons name="checkmark-circle" size={16} color={colors.onBrandSecondary} />
          <Text style={styles.matchText}>{t("stores_match")}</Text>
        </View>
      ) : null}
      {s.hours ? (
        <View style={styles.hoursRow}>
          <Ionicons name="time-outline" size={16} color={colors.muted} />
          <Text style={styles.hours}>{s.hours}</Text>
        </View>
      ) : null}
      <View style={styles.actions}>
        <Pressable style={styles.action} onPress={() => Linking.openURL(`tel:${s.phone}`)} testID={`store-call-${s.store_id}`}>
          <Ionicons name="call" size={18} color={colors.onSurface} />
          <Text style={styles.actionText}>{t("call")}</Text>
        </Pressable>
        {wa ? (
          <Pressable style={styles.action} onPress={() => Linking.openURL(`https://wa.me/${wa}`)} testID={`store-whatsapp-${s.store_id}`}>
            <Ionicons name="logo-whatsapp" size={18} color={colors.onSurface} />
            <Text style={styles.actionText}>{t("whatsapp")}</Text>
          </Pressable>
        ) : null}
        <Pressable style={[styles.action, styles.actionMain]} onPress={directions} testID={`store-directions-${s.store_id}`}>
          <Ionicons name="navigate" size={18} color={colors.onBrandPrimary} />
          <Text style={[styles.actionText, { color: colors.onBrandPrimary }]}>{t("stores_directions")}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, paddingBottom: 12, backgroundColor: c.surface },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 24, fontFamily: fonts.display, color: c.onSurface, flex: 1 },
  map: { height: "40%", width: "100%" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 14, paddingHorizontal: 28, paddingVertical: 40 },
  permIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  centerTitle: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface, textAlign: "center" },
  centerText: { fontSize: 15, lineHeight: 21, color: c.onSurfaceTertiary, textAlign: "center" },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 18, padding: 14, gap: 10, borderWidth: 1.5, borderColor: c.border },
  cardActive: { borderColor: c.brandPrimary },
  cardTop: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  photo: { width: 64, height: 64, borderRadius: 12, backgroundColor: c.surfaceTertiary },
  photoEmpty: { alignItems: "center", justifyContent: "center", backgroundColor: c.brandSecondary },
  name: { fontSize: 17, fontWeight: "700", color: c.onSurface },
  address: { fontSize: 14, color: c.onSurfaceTertiary },
  distance: { fontSize: 13, fontWeight: "700", color: c.brandTertiary },
  flag: { width: 36, height: 36, alignItems: "center", justifyContent: "center" },
  match: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: c.brandSecondary, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 },
  matchText: { fontSize: 13, fontWeight: "700", color: c.onBrandSecondary },
  hoursRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  hours: { fontSize: 13, color: c.onSurfaceTertiary, flex: 1 },
  actions: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  action: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 44, paddingHorizontal: 14, borderRadius: 999, backgroundColor: c.surfaceTertiary },
  actionMain: { backgroundColor: c.brandPrimary, marginLeft: "auto" },
  actionText: { fontSize: 14, fontWeight: "700", color: c.onSurface },
  chipsBar: { flexGrow: 0 },
  chips: { paddingHorizontal: 16, paddingBottom: 12, gap: 8 },
  chip: { minHeight: 40, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center" },
  chipOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontSize: 14, fontWeight: "600", color: c.onSurface },
  chipTextOn: { color: c.onBrandPrimary },
}));
