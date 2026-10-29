import React, { useCallback, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { useSeen } from "@/src/seen";
import { fmtMinutes, NewBadge, scheduleText } from "@/src/proUi";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { Avatar } from "@/src/ui";
import { LangToggle } from "@/src/LangToggle";
import { useMembership } from "@/src/membership";
import { HistoryList } from "@/src/HistoryList";
import { fmtDate } from "@/src/time";

type RowProps = {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  sub?: string;
  onPress: () => void;
  testID: string;
  danger?: boolean;
  isNew?: boolean;
};

function Row({ icon, title, sub, onPress, testID, danger, isNew }: RowProps) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surfaceTertiary }]}>
      <View style={[styles.rowIcon, danger && { backgroundColor: colors.surfaceTertiary }]}>
        <Ionicons name={icon} size={20} color={danger ? colors.error : colors.brandPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <View style={styles.rowTitleLine}>
          <Text style={[styles.rowTitle, danger && { color: colors.error }]}>{title}</Text>
          {isNew ? <NewBadge /> : null}
        </View>
        {sub ? <Text style={styles.rowSub}>{sub}</Text> : null}
      </View>
      {!danger && <Ionicons name="chevron-forward" size={18} color={colors.muted} />}
    </Pressable>
  );
}

function zoneSub(st: any, t: (k: string) => string, lang: string) {
  const where = st.zone.set ? `${st.zone.label || t("turin")} + ${st.zone.radius_km} km` : t("zone_not_set");
  return st.schedule_set ? `${where} · ${scheduleText(st.schedule, lang)}` : where;
}

function alertsCats(st: any, t: (k: string) => string) {
  const cats: string[] = st.alerts.categories || [];
  if (!cats.length) return t("alerts_none");
  if (cats.length === st.categories.length && cats.length > 1) return t("alerts_all");
  return `${t("only")} ${cats.map((c) => t(`cat_${c}`).toLowerCase()).join(", ")}`;
}

export default function Profile() {
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { user, logout } = useAuth();
  const { t, lang } = useI18n();
  const isSpec = !!(user?.role === "specialist" && user.specialist_id);
  const membership = useMembership(!!isSpec);
  const spec = useQuery({ queryKey: ["specialist-me"], queryFn: () => api<any>("/specialists/me"), enabled: !!isSpec });
  const settings = useQuery({ queryKey: ["pro-settings", lang], queryFn: () => api<any>(`/specialists/me/settings?lang=${lang}`), enabled: !!isSpec });
  const stats = useQuery({ queryKey: ["pro-stats", "7"], queryFn: () => api<any>("/specialists/me/stats?days=7"), enabled: !!isSpec });
  const seenStats = useSeen("pro_stats");
  const seenZone = useSeen("pro_zone");
  const seenReplies = useSeen("pro_replies");
  const seenAlerts = useSeen("pro_alerts");
  const seenFeatured = useSeen("pro_featured");
  useFocusEffect(
    useCallback(() => {
      [seenStats, seenZone, seenReplies, seenAlerts, seenFeatured].forEach((x) => x.reload());
      if (isSpec) {
        stats.refetch();
        settings.refetch();
        spec.refetch();
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isSpec]),
  );
  const [tab, setTab] = useState<"account" | "history">("account");
  const { colors } = useTheme();
  const it = lang === "it";
  const sp = spec.data;
  const st = settings.data;
  const wk = stats.data;
  const [delOpen, setDelOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const confirmDelete = async () => {
    setBusy(true);
    setErr("");
    try {
      await api("/auth/delete-account", { method: "POST", body: { password: pw || null } });
      setDelOpen(false);
      await logout();
    } catch (e: any) {
      setErr(e?.message || (it ? "Errore. Riprova." : "Error. Inténtalo de nuevo."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>{t("profile_title")}</Text>
        <View style={styles.seg}>
          {(["account", "history"] as const).map((k) => (
            <Pressable key={k} testID={`profile-tab-${k}`} onPress={() => setTab(k)} style={[styles.segItem, tab === k && styles.segOn]}>
              <Text style={[styles.segText, tab === k && styles.segTextOn]}>{t(k === "account" ? "tab_account" : "tab_history")}</Text>
            </Pressable>
          ))}
        </View>
      </View>
      {tab === "history" ? (
        <HistoryList bottom={bottomChrome} />
      ) : (
      <ScrollView contentContainerStyle={{ padding: 16, gap: 24, paddingBottom: bottomChrome + 24 }}>
        {isSpec ? (
          <View style={styles.userCard}>
            <Avatar uri={sp?.avatar || user?.picture} name={sp?.name || user?.name} size={64} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={styles.name} testID="profile-name">
                {sp?.name || user?.name}
              </Text>
              <Text style={styles.email}>
                {(sp?.categories || []).map((c: string) => t(`pro_cat_${c}`)).join(", ")} · {t("turin")}
              </Text>
              <View style={[styles.avail, !sp?.available_now && styles.availOff]} testID="profile-availability">
                <View style={[styles.availDot, !sp?.available_now && styles.availDotOff]} />
                <Text style={[styles.availText, !sp?.available_now && styles.availTextOff]}>
                  {sp?.available_now ? t("available_now") : sp && !sp.membership_active ? t("mb_inactive") : t("out_of_hours")}
                </Text>
              </View>
            </View>
          </View>
        ) : (
          <View style={styles.userCard}>
            <Avatar uri={user?.picture} name={user?.name} size={64} />
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={styles.name} testID="profile-name">
                {user?.name}
              </Text>
              <Text style={styles.email}>{user?.email}</Text>
              <View style={styles.role}>
                <Text style={styles.roleText} testID="profile-role">
                  {t("role_client")}
                </Text>
              </View>
            </View>
          </View>
        )}

        {isSpec && (
          <View style={{ gap: 10 }}>
            <View style={styles.weekHead}>
              <View style={styles.rowTitleLine}>
                <Text style={styles.weekTitle}>{t("this_week")}</Text>
                {seenStats.isNew ? <NewBadge /> : null}
              </View>
              <Pressable testID="stats-details" hitSlop={8} onPress={() => router.push("/pro-stats")}>
                <Text style={styles.details}>{t("details")} ›</Text>
              </Pressable>
            </View>
            <Pressable onPress={() => router.push("/pro-stats")} style={styles.tiles} testID="week-tiles">
              <View style={styles.tile}>
                <Text style={styles.tileNum}>{wk ? wk.views : "–"}</Text>
                <Text style={styles.tileLabel}>{t("stat_views")}</Text>
                {wk?.views_change_pct != null && wk.views_change_pct !== 0 ? (
                  <Text style={[styles.up, wk.views_change_pct < 0 && styles.down]}>
                    {wk.views_change_pct > 0 ? "▲" : "▼"} {Math.abs(wk.views_change_pct)}%
                  </Text>
                ) : null}
              </View>
              <View style={styles.tile}>
                <Text style={styles.tileNum}>{wk ? wk.clients : "–"}</Text>
                <Text style={styles.tileLabel}>{t("stat_clients")}</Text>
                {wk?.clients_change ? (
                  <Text style={[styles.up, wk.clients_change < 0 && styles.down]}>
                    {wk.clients_change > 0 ? "▲" : "▼"} {Math.abs(wk.clients_change)}
                  </Text>
                ) : null}
              </View>
              <View style={styles.tile}>
                <Text style={styles.tileNum}>{wk?.response_avg_min != null ? fmtMinutes(wk.response_avg_min) : "–"}</Text>
                <Text style={styles.tileLabel}>{t("stat_response")}</Text>
              </View>
            </Pressable>
          </View>
        )}

        {isSpec ? (
          <>
            <View style={styles.group}>
              <Row testID="my-specialist-profile-row" icon="id-card-outline" title={t("my_specialist_profile")} onPress={() => router.push({ pathname: "/specialist/[id]", params: { id: user!.specialist_id! } })} />
              <View style={styles.sep} />
              <Row testID="edit-specialist-row" icon="create-outline" title={t("edit_profile_short")} onPress={() => router.push("/specialist-form")} />
              <View style={styles.sep} />
              <Row
                testID="zone-row"
                icon="location-outline"
                title={t("zone_hours")}
                sub={st ? zoneSub(st, t, lang) : undefined}
                isNew={seenZone.isNew}
                onPress={() => router.push("/pro-zone")}
              />
              <View style={styles.sep} />
              <Row
                testID="quick-replies-row"
                icon="flash-outline"
                title={t("quick_replies")}
                sub={st ? t("quick_replies_count").replace("{n}", String(st.quick_replies.length)) : undefined}
                isNew={seenReplies.isNew}
                onPress={() => router.push("/pro-replies")}
              />
              <View style={styles.sep} />
              <Row
                testID="alerts-row"
                icon="notifications-outline"
                title={t("alerts_title")}
                sub={st ? (st.alerts.enabled ? `${t("alerts_on")} · ${alertsCats(st, t)}` : t("alerts_off")) : undefined}
                isNew={seenAlerts.isNew}
                onPress={() => router.push("/pro-alerts")}
              />
            </View>
            <View style={styles.group}>
              <Row
                testID="membership-row"
                icon="ribbon-outline"
                title={t("membership")}
                sub={membership.data ? (membership.data.active ? `${t("active_until")} ${fmtDate(membership.data.expires_at!, lang)}` : t("mb_inactive")) : undefined}
                onPress={() => router.push("/membership")}
              />
              <View style={styles.sep} />
              <Row
                testID="featured-row"
                icon="star-outline"
                title={t("featured_title")}
                sub={
                  st?.featured_until
                    ? `${t("featured_until")} ${fmtDate(st.featured_until, lang)}`
                    : t("featured_sub").replace("{trade}", t(`pro_cats_${(sp?.categories || ["plumbing"])[0]}`))
                }
                isNew={seenFeatured.isNew}
                onPress={() => router.push("/pro-featured")}
              />
            </View>
          </>
        ) : null}

        <View style={styles.group}>
          <View style={styles.langRow}>
            <Ionicons name="language" size={20} color={styles.langIcon.color} />
            <Text style={[styles.rowTitle, { flex: 1 }]}>{t("language")}</Text>
            <LangToggle />
          </View>
        </View>

        <View style={styles.group}>
          <Row testID="logout-button" icon="log-out-outline" title={t("logout")} onPress={logout} danger />
          <View style={styles.sep} />
          <Row
            testID="delete-account-button"
            icon="trash-outline"
            title={it ? "Elimina account" : "Eliminar cuenta"}
            onPress={() => {
              setPw("");
              setErr("");
              setDelOpen(true);
            }}
            danger
          />
        </View>
      </ScrollView>
      )}
      <Modal visible={delOpen} transparent animationType="fade" onRequestClose={() => !busy && setDelOpen(false)}>
        <View style={styles.modalBack}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>{it ? "Eliminare l'account?" : "¿Eliminar tu cuenta?"}</Text>
            <Text style={styles.modalText}>
              {it
                ? "Verranno eliminati in modo permanente i tuoi dati, le diagnosi, le foto, le conversazioni e, se sei uno specialista, il tuo profilo. Non si può annullare."
                : "Se borrarán de forma permanente tus datos, diagnósticos, fotos, conversaciones y, si eres especialista, tu perfil. No se puede deshacer."}
            </Text>
            <Text style={styles.modalText}>
              {it ? "Se hai creato l'account con email e password, inserisci la password. Se hai usato Google, lascia vuoto." : "Si creaste tu cuenta con correo y contraseña, escribe tu contraseña. Si entraste con Google, déjalo vacío."}
            </Text>
            <TextInput
              testID="delete-password-input"
              value={pw}
              onChangeText={setPw}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              placeholder={it ? "Password" : "Contraseña"}
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
            {err ? <Text style={styles.errText}>{err}</Text> : null}
            <View style={styles.btnRow}>
              <Pressable testID="delete-cancel" disabled={busy} onPress={() => setDelOpen(false)} style={[styles.btn, { backgroundColor: colors.surfaceTertiary }]}>
                <Text style={[styles.btnText, { color: colors.onSurface }]}>{it ? "Annulla" : "Cancelar"}</Text>
              </Pressable>
              <Pressable testID="delete-confirm" disabled={busy} onPress={confirmDelete} style={[styles.btn, { backgroundColor: colors.error }]}>
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={[styles.btnText, { color: "#fff" }]}>{it ? "Elimina" : "Eliminar"}</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 24, paddingBottom: 8, gap: 12 },
  seg: { flexDirection: "row", backgroundColor: c.surfaceTertiary, borderRadius: 12, padding: 3 },
  segItem: { flex: 1, minHeight: 40, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  segOn: { backgroundColor: c.surfaceSecondary },
  segText: { fontSize: 14, fontWeight: "600", color: c.onSurfaceTertiary },
  segTextOn: { color: c.brandPrimary },
  title: { fontSize: 28, fontFamily: fonts.display, color: c.onSurface, letterSpacing: -0.6 },
  userCard: { flexDirection: "row", alignItems: "center", gap: 16, padding: 16, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  name: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  email: { fontSize: 14, color: c.muted },
  role: { alignSelf: "flex-start", backgroundColor: c.brandSecondary, paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, marginTop: 2 },
  roleText: { color: c.onBrandSecondary, fontWeight: "700", fontSize: 12 },
  group: { borderRadius: 12, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, overflow: "hidden" },
  langRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, minHeight: 60 },
  langIcon: { color: c.brandPrimary },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 12, minHeight: 60 },
  rowIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: 16, fontWeight: "600", color: c.onSurface, flexShrink: 1 },
  rowTitleLine: { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" },
  avail: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: "#E7F6EC", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, marginTop: 4 },
  availOff: { backgroundColor: c.surfaceTertiary },
  availDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#16794A" },
  availDotOff: { backgroundColor: c.muted },
  availText: { fontSize: 12, fontWeight: "700", color: "#16794A" },
  availTextOff: { color: c.onSurfaceTertiary },
  weekHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  weekTitle: { fontSize: 18, fontFamily: fonts.display, color: c.onSurface },
  details: { color: c.brandTertiary, fontWeight: "700", fontSize: 13 },
  tiles: { flexDirection: "row", gap: 8 },
  tile: { flex: 1, backgroundColor: c.surfaceInverse, borderRadius: 14, padding: 12, gap: 2 },
  tileNum: { color: c.onSurfaceInverse, fontSize: 24, fontFamily: fonts.display },
  tileLabel: { color: "#B8C2D3", fontSize: 12, lineHeight: 16 },
  up: { color: "#4ADE80", fontSize: 11, fontWeight: "700", marginTop: 2 },
  down: { color: "#FCA5A5" },
  rowSub: { fontSize: 13, color: c.muted, marginTop: 2 },
  sep: { height: 1, backgroundColor: c.divider, marginLeft: 64 },
  modalBack: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", alignItems: "center", justifyContent: "center", padding: 24 },
  modalCard: { width: "100%", maxWidth: 420, borderRadius: 20, backgroundColor: c.surfaceSecondary, padding: 20, gap: 12 },
  modalTitle: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  modalText: { fontSize: 14, color: c.muted, lineHeight: 20 },
  input: { minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: c.border, paddingHorizontal: 14, color: c.onSurface, fontSize: 16 },
  errText: { color: c.error, fontSize: 14 },
  btnRow: { flexDirection: "row", gap: 12, marginTop: 4 },
  btn: { flex: 1, minHeight: 48, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  btnText: { fontSize: 16, fontWeight: "700" },
}));