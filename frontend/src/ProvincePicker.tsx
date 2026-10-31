import React, { useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import * as Location from "expo-location";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { Place, saveMyProvince } from "@/src/province";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { Button } from "@/src/ui";

// "Dove ti trovi?": the client picks their province with the phone location or by typing their comune.
export function ProvincePicker({ onDone, onCancel }: { onDone?: () => void; onCancel?: () => void }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [results, setResults] = useState<Place[] | null>(null);
  const [selected, setSelected] = useState<Place | null>(null);
  const [busy, setBusy] = useState<null | "gps" | "search" | "save">(null);
  const [error, setError] = useState<string | null>(null);

  const useLocation = async () => {
    setError(null);
    setBusy("gps");
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) {
        setError(t("prov_location_denied"));
        return;
      }
      const pos =
        (await Location.getLastKnownPositionAsync({ maxAge: 30 * 60 * 1000 })) ??
        (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }));
      await saveMyProvince(pos.coords.latitude, pos.coords.longitude);
      onDone?.();
    } catch (e: any) {
      setError(e?.message && !String(e.message).startsWith("Error") ? e.message : t("prov_location_failed"));
    } finally {
      setBusy(null);
    }
  };

  const search = async () => {
    const q = text.trim();
    if (q.length < 2) return;
    setError(null);
    setSelected(null);
    setBusy("search");
    try {
      const r = await api<Place[]>(`/places/search?q=${encodeURIComponent(q)}`);
      setResults(r);
      if (r.length === 1) setSelected(r[0]);
    } catch (e: any) {
      setError(e?.message || t("error_generic"));
    } finally {
      setBusy(null);
    }
  };

  const confirm = async () => {
    if (!selected) return;
    setError(null);
    setBusy("save");
    try {
      await saveMyProvince(selected.lat, selected.lng);
      onDone?.();
    } catch (e: any) {
      setError(e?.message || t("error_generic"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={styles.sheet} testID="province-picker">
      <Text style={styles.title}>{t("prov_where_title")}</Text>
      <Text style={styles.sub}>{t("prov_where_sub")}</Text>
      <Button title={t("prov_use_location")} icon="locate" onPress={useLocation} loading={busy === "gps"} disabled={!!busy} testID="province-use-location" />
      <View style={styles.orRow}>
        <View style={styles.orLine} />
        <Text style={styles.orText}>{t("prov_or")}</Text>
        <View style={styles.orLine} />
      </View>
      <View style={styles.inputRow}>
        <TextInput
          testID="province-city-input"
          value={text}
          onChangeText={(v) => {
            setText(v);
            setResults(null);
            setSelected(null);
          }}
          onSubmitEditing={search}
          placeholder={t("prov_city_ph")}
          placeholderTextColor={colors.muted}
          returnKeyType="search"
          autoCorrect={false}
          style={styles.input}
        />
        <Pressable testID="province-search" onPress={search} disabled={!!busy || text.trim().length < 2} style={[styles.searchBtn, text.trim().length < 2 && { opacity: 0.5 }]}>
          {busy === "search" ? <ActivityIndicator color={colors.onSurfaceInverse} /> : <Ionicons name="search" size={18} color={colors.onSurfaceInverse} />}
        </Pressable>
      </View>
      {results && results.length === 0 ? <Text style={styles.sub}>{t("prov_no_results")}</Text> : null}
      {results && results.length > 0 ? (
        <View style={styles.list}>
          {results.map((p, i) => {
            const on = selected === p;
            return (
              <Pressable
                key={`${p.name}-${p.province.code}`}
                testID={`province-result-${i}`}
                onPress={() => setSelected(p)}
                style={[styles.row, i > 0 && styles.rowBorder, on && styles.rowOn]}
                accessibilityRole="radio"
                accessibilityState={{ selected: on }}
              >
                <Text style={styles.rowName} numberOfLines={1}>
                  {p.name}
                </Text>
                <Text style={styles.rowProv} numberOfLines={1}>
                  {t("prov_of").replace("{p}", p.province.name)}
                </Text>
                {on ? <Ionicons name="checkmark-circle" size={18} color={colors.brandPrimary} /> : null}
              </Pressable>
            );
          })}
        </View>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {selected ? (
        <Pressable testID="province-confirm" onPress={confirm} disabled={!!busy} style={styles.confirm}>
          {busy === "save" ? <ActivityIndicator color={colors.onSurfaceInverse} /> : <Text style={styles.confirmText}>{t("prov_confirm")}</Text>}
        </Pressable>
      ) : null}
      {onCancel ? (
        <Pressable testID="province-cancel" onPress={onCancel} style={styles.cancel} hitSlop={6}>
          <Text style={styles.cancelText}>{t("prov_cancel")}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  sheet: { backgroundColor: c.surfaceSecondary, borderRadius: 20, borderWidth: 1, borderColor: c.border, padding: 18, gap: 12 },
  title: { fontSize: 24, fontFamily: fonts.display, color: c.onSurface, letterSpacing: -0.4 },
  sub: { fontSize: 14, color: c.muted, lineHeight: 20 },
  orRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  orLine: { flex: 1, height: 1, backgroundColor: c.border },
  orText: { fontSize: 13, color: c.muted },
  inputRow: { flexDirection: "row", gap: 8 },
  input: { flex: 1, minHeight: 48, borderWidth: 1.5, borderColor: c.borderStrong, borderRadius: 12, paddingHorizontal: 12, fontSize: 16, color: c.onSurface, backgroundColor: c.surfaceSecondary },
  searchBtn: { width: 48, height: 48, borderRadius: 12, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  list: { borderWidth: 1, borderColor: c.border, borderRadius: 12, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, minHeight: 48 },
  rowBorder: { borderTopWidth: 1, borderTopColor: c.border },
  rowOn: { backgroundColor: c.brandSecondary },
  rowName: { fontSize: 15, fontWeight: "700", color: c.onSurface, flexShrink: 1 },
  rowProv: { fontSize: 13, color: c.muted, flex: 1, textAlign: "right" },
  error: { fontSize: 14, color: c.error },
  confirm: { height: 50, borderRadius: 999, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  confirmText: { color: c.onSurfaceInverse, fontWeight: "700", fontSize: 16 },
  cancel: { alignSelf: "center", minHeight: 36, justifyContent: "center" },
  cancelText: { color: c.muted, fontWeight: "600", fontSize: 14 },
}));
