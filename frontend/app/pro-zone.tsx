import React, { useEffect, useRef, useState } from "react";
import { Modal, PanResponder, Platform, Pressable, ScrollView, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import Constants from "expo-constants";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { Button, Loading } from "@/src/ui";
import { DAY_LETTERS } from "@/src/proUi";
import { markSeen } from "@/src/seen";
import { useMyPosition } from "@/src/position";

const HAS_MAPS_KEY = Boolean(Constants.expoConfig?.extra?.hasMapsKey);
const Maps: typeof import("react-native-maps") | null =
  Platform.OS === "web" || !HAS_MAPS_KEY ? null : require("react-native-maps");
const MIN_KM = 1;
const MAX_KM = 30;
const TIMES = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);

// Where the specialist works (centre + radius) and when: clients outside the zone don't see them in the list.
export default function ProZone() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, lang } = useI18n();
  const toast = useToast();
  const me = useMyPosition();
  const q = useQuery({ queryKey: ["pro-settings", lang], queryFn: () => api<any>(`/specialists/me/settings?lang=${lang}`) });
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(null);
  const [radius, setRadius] = useState(8);
  const [days, setDays] = useState<number[]>([1, 2, 3, 4, 5, 6]);
  const [from, setFrom] = useState("08:00");
  const [to, setTo] = useState("19:00");
  const [urgent, setUrgent] = useState(false);
  const [picker, setPicker] = useState<null | "from" | "to">(null);
  const [busy, setBusy] = useState(false);
  const loaded = useRef(false);

  useEffect(() => {
    markSeen("pro_zone");
  }, []);

  useEffect(() => {
    const st = q.data;
    if (!st || loaded.current) return;
    loaded.current = true;
    setCenter({ lat: st.zone.lat, lng: st.zone.lng });
    setRadius(Math.round(st.zone.radius_km));
    setDays(st.schedule.days);
    setFrom(st.schedule.from);
    setTo(st.schedule.to);
    setUrgent(st.urgent);
  }, [q.data]);

  // First time (zone never saved): start from where the specialist is now.
  useEffect(() => {
    if (q.data && !q.data.zone.set && me.pos) setCenter(me.pos);
  }, [q.data, me.pos]);

  const save = async () => {
    if (!center) return;
    if (!days.length) return toast(t("zone_pick_day"), "error");
    if (from >= to) return toast(t("zone_bad_hours"), "error");
    setBusy(true);
    try {
      await api("/specialists/me/zone", {
        method: "PUT",
        body: { lat: center.lat, lng: center.lng, radius_km: radius, days, from, to, urgent },
      });
      queryClient.invalidateQueries({ queryKey: ["pro-settings"] });
      queryClient.invalidateQueries({ queryKey: ["specialist-me"] });
      toast(t("saved"));
      router.back();
    } catch (e: any) {
      toast(e.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (q.isLoading || !center) return <Loading />;

  return (
    <View style={styles.root}>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="zone-back" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("zone_hours")}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <Text style={styles.lbl}>{t("zone_where")}</Text>
        <View style={styles.map}>
          {Maps ? (
            <Maps.default
              style={StyleSheetAbs}
              initialRegion={{ latitude: center.lat, longitude: center.lng, latitudeDelta: 0.25, longitudeDelta: 0.25 }}
              onRegionChangeComplete={(r) => setCenter({ lat: r.latitude, lng: r.longitude })}
              toolbarEnabled={false}
            >
              <Maps.Circle
                center={{ latitude: center.lat, longitude: center.lng }}
                radius={radius * 1000}
                strokeColor={colors.brandPrimary}
                strokeWidth={2}
                fillColor="rgba(255,107,0,0.18)"
              />
            </Maps.default>
          ) : (
            <View style={[StyleSheetAbs, styles.mapFallback]}>
              <View style={[styles.circle, { width: 60 + radius * 4, height: 60 + radius * 4, borderRadius: 30 + radius * 2 }]} />
            </View>
          )}
          <View pointerEvents="none" style={styles.pinWrap}>
            <View style={styles.pin} />
          </View>
        </View>
        {Maps ? <Text style={styles.hint}>{t("zone_move_map")}</Text> : null}

        <View style={styles.card}>
          <View style={styles.between}>
            <Text style={styles.cardText}>{t("zone_radius")}</Text>
            <Text style={styles.cardBold}>{radius} km</Text>
          </View>
          <Slider value={radius} onChange={setRadius} />
          <Text style={styles.note}>{t("zone_radius_note")}</Text>
        </View>

        <Text style={styles.lbl}>{t("zone_days")}</Text>
        <View style={styles.days}>
          {(DAY_LETTERS[lang] || DAY_LETTERS.it).map((l, i) => {
            const d = i + 1;
            const on = days.includes(d);
            return (
              <Pressable
                key={d}
                testID={`zone-day-${d}`}
                onPress={() => setDays(on ? days.filter((x) => x !== d) : [...days, d].sort())}
                style={[styles.day, on && styles.dayOn]}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
              >
                <Text style={[styles.dayText, on && styles.dayTextOn]}>{l}</Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={styles.lbl}>{t("zone_hours_label")}</Text>
        <View style={styles.hours}>
          <Pressable testID="zone-from" onPress={() => setPicker("from")} style={styles.hourBox}>
            <Text style={styles.hourSmall}>{t("from_time")}</Text>
            <Text style={styles.hourVal}>{from}</Text>
          </Pressable>
          <Pressable testID="zone-to" onPress={() => setPicker("to")} style={styles.hourBox}>
            <Text style={styles.hourSmall}>{t("to_time")}</Text>
            <Text style={styles.hourVal}>{to}</Text>
          </Pressable>
        </View>

        <View style={[styles.card, styles.urgentRow]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.urgentTitle}>{t("urgent_title")}</Text>
            <Text style={styles.note}>{t("urgent_sub")}</Text>
          </View>
          <Switch
            testID="zone-urgent"
            value={urgent}
            onValueChange={setUrgent}
            trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
            thumbColor="#FFFFFF"
          />
        </View>
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + 12 }]}>
        <Button testID="zone-save" title={t("save")} onPress={save} loading={busy} />
      </View>

      <Modal visible={!!picker} transparent animationType="fade" onRequestClose={() => setPicker(null)}>
        <Pressable style={styles.backdrop} onPress={() => setPicker(null)}>
          <View style={styles.pickerCard}>
            <Text style={styles.pickerTitle}>{picker === "from" ? t("from_time") : t("to_time")}</Text>
            <ScrollView style={{ maxHeight: 360 }}>
              {(picker === "to" ? [...TIMES.slice(1), "24:00"] : TIMES).map((v) => {
                const on = (picker === "from" ? from : to) === v;
                return (
                  <Pressable
                    key={v}
                    onPress={() => {
                      picker === "from" ? setFrom(v) : setTo(v);
                      setPicker(null);
                    }}
                    style={[styles.timeRow, on && { backgroundColor: colors.brandSecondary }]}
                  >
                    <Text style={[styles.timeText, on && { color: colors.onBrandSecondary, fontWeight: "700" }]}>{v}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

function Slider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const styles = useStyles();
  const width = useRef(1);
  const set = (x: number) => {
    const p = Math.min(1, Math.max(0, x / width.current));
    onChange(Math.round(MIN_KM + p * (MAX_KM - MIN_KM)));
  };
  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (e) => set(e.nativeEvent.locationX),
      onPanResponderMove: (e) => set(e.nativeEvent.locationX),
      onPanResponderTerminationRequest: () => false,
    }),
  ).current;
  const pct = ((value - MIN_KM) / (MAX_KM - MIN_KM)) * 100;
  return (
    <View
      {...pan.panHandlers}
      onLayout={(e) => (width.current = e.nativeEvent.layout.width)}
      style={styles.sliderHit}
      testID="zone-radius"
      accessibilityRole="adjustable"
      accessibilityValue={{ min: MIN_KM, max: MAX_KM, now: value, text: `${value} km` }}
      accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
      onAccessibilityAction={(e) => onChange(Math.min(MAX_KM, Math.max(MIN_KM, value + (e.nativeEvent.actionName === "increment" ? 1 : -1))))}
    >
      <View pointerEvents="none" style={styles.track}>
        <View style={[styles.fill, { width: `${pct}%` }]} />
      </View>
      <View pointerEvents="none" style={[styles.thumb, { left: `${pct}%` }]} />
    </View>
  );
}

const StyleSheetAbs = { position: "absolute" as const, top: 0, left: 0, right: 0, bottom: 0 };

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  top: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 4 },
  back: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  body: { padding: 16, gap: 14, paddingBottom: 24 },
  lbl: { fontSize: 13, fontWeight: "700", color: c.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 0.4 },
  map: { height: 150, borderRadius: 16, overflow: "hidden", backgroundColor: "#E6EBF2" },
  mapFallback: { backgroundColor: "#DDE4EE", alignItems: "center", justifyContent: "center" },
  circle: { backgroundColor: "rgba(255,107,0,0.18)", borderWidth: 2, borderColor: c.brandPrimary },
  pinWrap: { ...StyleSheetAbs, alignItems: "center", justifyContent: "center" },
  pin: { width: 14, height: 14, borderRadius: 7, backgroundColor: c.brandPrimary, borderWidth: 3, borderColor: "#FFFFFF" },
  hint: { fontSize: 12, color: c.muted, marginTop: -8 },
  card: { backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 18, padding: 14, gap: 12 },
  between: { flexDirection: "row", justifyContent: "space-between" },
  cardText: { fontSize: 15, color: c.onSurface },
  cardBold: { fontSize: 15, fontWeight: "700", color: c.onSurface },
  note: { fontSize: 13, color: c.muted, lineHeight: 18 },
  sliderHit: { height: 28, justifyContent: "center" },
  track: { height: 6, borderRadius: 3, backgroundColor: c.border, overflow: "hidden" },
  fill: { height: 6, backgroundColor: c.brandPrimary },
  thumb: { position: "absolute", width: 22, height: 22, marginLeft: -11, borderRadius: 11, backgroundColor: "#FFFFFF", borderWidth: 2, borderColor: c.brandPrimary },
  days: { flexDirection: "row", gap: 6 },
  day: { flex: 1, height: 40, borderRadius: 10, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, alignItems: "center", justifyContent: "center" },
  dayOn: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  dayText: { fontSize: 13, fontWeight: "700", color: c.onSurface },
  dayTextOn: { color: c.onSurfaceInverse },
  hours: { flexDirection: "row", gap: 10 },
  hourBox: { flex: 1, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 12, paddingVertical: 10, paddingHorizontal: 12 },
  hourSmall: { fontSize: 12, color: c.muted },
  hourVal: { fontSize: 15, color: c.onSurface },
  urgentRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  urgentTitle: { fontSize: 15, fontWeight: "600", color: c.onSurface },
  footer: { paddingHorizontal: 16, paddingTop: 8 },
  backdrop: { flex: 1, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center", padding: 32 },
  pickerCard: { width: "100%", maxWidth: 320, backgroundColor: c.surfaceSecondary, borderRadius: 20, padding: 16, gap: 8 },
  pickerTitle: { fontSize: 18, fontFamily: fonts.display, color: c.onSurface },
  timeRow: { paddingVertical: 12, paddingHorizontal: 12, borderRadius: 10 },
  timeText: { fontSize: 16, color: c.onSurface },
}));
