// Private admin dashboard: how many people use BE HAPPY. Opened at /admin and protected by the server's
// ADMIN_TOKEN (sent as X-Admin-Token), not by the app login. Admin-only, so the texts are in Spanish only.
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { API } from "@/src/api";
import { storage } from "@/src/utils/storage";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { Button } from "@/src/ui";

const KEY = "behappy.admin-token";
const CAT: Record<string, string> = {
  plumbing: "Fontanería", electrical: "Electricidad", hvac: "Climatización", masonry: "Obra", carpentry: "Carpintería",
};

type Day = { day: string; new_users: number; active_users: number; diagnoses: number; requests: number; ai_grok: number; ai_gemini: number };
type Stats = {
  generated_at: string;
  days: number;
  users: Record<"total" | "specialists" | "new_today" | "new_7d" | "new_30d" | "active_today" | "active_7d" | "active_30d", number>;
  diagnoses: { total: number; today: number; last_7d: number; failed_7d: number; top_categories_30d: { category: string; count: number }[] };
  ai: { primary: string; grok_today: number; gemini_today: number; grok_daily_cap: number; gemini_daily_cap: number };
  specialists: Record<"total" | "active_membership" | "verified" | "in_review", number>;
  marketplace: Record<"requests_total" | "requests_open" | "requests_30d" | "quotes_30d" | "quotes_accepted_30d" | "conversations_total" | "conversations_30d", number>;
  stores: { on_map: number; pending: number };
  series: Day[];
};

// The token is a password: Keychain/Keystore on the phone app; in the browser, this device's storage.
const loadToken = () => (Platform.OS === "web" ? storage.getItem<string>(KEY, "") : storage.secureGet<string>(KEY, ""));
const saveToken = (v: string) => (Platform.OS === "web" ? storage.setItem(KEY, v) : storage.secureSet(KEY, v));
const clearToken = () => (Platform.OS === "web" ? storage.removeItem(KEY) : storage.secureRemove(KEY));

async function fetchStats(token: string): Promise<Stats> {
  const res = await fetch(`${API}/admin/stats?days=30`, { headers: { "X-Admin-Token": token } });
  if (res.status === 403) throw new Error("Clave incorrecta");
  if (!res.ok) throw new Error(`Error ${res.status}`);
  return res.json();
}

const fmtDay = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;

export default function Admin() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [token, setToken] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [data, setData] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [table, setTable] = useState(false);

  const load = useCallback(async (t: string) => {
    setLoading(true);
    setError("");
    try {
      setData(await fetchStats(t));
      return true;
    } catch (e: any) {
      setError(e?.message || "Error");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadToken().then((t) => {
      setToken(t || "");
      if (t) void load(t);
    });
  }, [load]);

  // Refresh every minute while the page is open.
  useEffect(() => {
    if (!token) return;
    const h = setInterval(() => void load(token), 60_000);
    return () => clearInterval(h);
  }, [token, load]);

  const enter = async () => {
    const t = draft.trim();
    if (!t) return;
    if (await load(t)) {
      await saveToken(t);
      setToken(t);
      setDraft("");
    }
  };
  const exit = async () => {
    await clearToken();
    setToken("");
    setData(null);
  };

  if (token === null) return <View style={styles.root}><ActivityIndicator style={{ marginTop: 80 }} color={colors.brandPrimary} /></View>;

  if (!token || (!data && error === "Clave incorrecta")) {
    return (
      <View style={[styles.root, styles.center, { paddingTop: insets.top + 24 }]}>
        <View style={styles.loginCard}>
          <Ionicons name="lock-closed-outline" size={28} color={colors.brandPrimary} />
          <Text style={styles.title}>Panel BE HAPPY</Text>
          <Text style={styles.muted}>Introduce la clave de administrador (ADMIN_TOKEN de Render).</Text>
          <TextInput
            testID="admin-token-input"
            value={draft}
            onChangeText={setDraft}
            onSubmitEditing={() => void enter()}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="Clave de administrador"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Button testID="admin-enter" title="Entrar" icon="log-in-outline" loading={loading} onPress={() => void enter()} />
        </View>
      </View>
    );
  }

  const s = data;
  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={[styles.page, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 32 }]}
      refreshControl={<RefreshControl refreshing={loading && !!s} onRefresh={() => void load(token)} tintColor={colors.brandPrimary} />}
    >
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Panel BE HAPPY</Text>
          <Text style={styles.muted}>
            {s ? `Actualizado ${new Date(s.generated_at).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })} · se actualiza cada minuto` : "Cargando…"}
          </Text>
        </View>
        <Pressable onPress={() => void load(token)} style={styles.iconBtn} accessibilityLabel="Actualizar">
          {loading ? <ActivityIndicator color={colors.brandPrimary} /> : <Ionicons name="refresh" size={20} color={colors.brandPrimary} />}
        </Pressable>
        <Pressable onPress={() => void exit()} style={styles.iconBtn} accessibilityLabel="Salir">
          <Ionicons name="log-out-outline" size={20} color={colors.brandPrimary} />
        </Pressable>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {s ? (
        <>
          <Section title="Personas">
            <Tiles items={[
              ["Activas hoy", s.users.active_today],
              ["Activas 7 días", s.users.active_7d],
              ["Activas 30 días", s.users.active_30d],
              ["Cuentas en total", s.users.total],
              ["Nuevas hoy", s.users.new_today],
              ["Nuevas 7 días", s.users.new_7d],
            ]} />
            <Bars title="Personas activas por día" series={s.series} pick={(d) => d.active_users} />
            <Bars title="Cuentas nuevas por día" series={s.series} pick={(d) => d.new_users} />
            <Text style={styles.note}>«Activa» = abrió la app con sesión ese día. Se cuenta desde que existe este panel.</Text>
          </Section>

          <Section title="Diagnósticos">
            <Tiles items={[
              ["Hoy", s.diagnoses.today],
              ["Últimos 7 días", s.diagnoses.last_7d],
              ["Fallidos 7 días", s.diagnoses.failed_7d],
              ["En total", s.diagnoses.total],
            ]} />
            <Bars title="Diagnósticos por día" series={s.series} pick={(d) => d.diagnoses} />
            {s.diagnoses.top_categories_30d.length ? (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Oficios más pedidos (30 días)</Text>
                {s.diagnoses.top_categories_30d.map((c) => (
                  <Rank key={c.category} label={CAT[c.category] ?? c.category} value={c.count} max={s.diagnoses.top_categories_30d[0].count} />
                ))}
              </View>
            ) : null}
          </Section>

          <Section title="Inteligencia artificial">
            <Tiles items={[
              [`Grok hoy (tope ${s.ai.grok_daily_cap})`, s.ai.grok_today],
              [`Gemini hoy (tope ${s.ai.gemini_daily_cap})`, s.ai.gemini_today],
            ]} />
            <View style={styles.twoCol}>
              <Bars compact title="Grok por día" series={s.series} pick={(d) => d.ai_grok} />
              <Bars compact title="Gemini por día" series={s.series} pick={(d) => d.ai_gemini} />
            </View>
            <Text style={styles.note}>Principal: {s.ai.primary === "grok" ? "Grok (Gemini de reserva)" : "Gemini"}. Incluye diagnósticos y traducciones.</Text>
          </Section>

          <Section title="Especialistas">
            <Tiles items={[
              ["Registrados", s.specialists.total],
              ["Membresía activa", s.specialists.active_membership],
              ["Verificados", s.specialists.verified],
              ["Verificación pendiente", s.specialists.in_review],
            ]} />
          </Section>

          <Section title="Solicitudes y chats">
            <Tiles items={[
              ["Solicitudes abiertas", s.marketplace.requests_open],
              ["Solicitudes 30 días", s.marketplace.requests_30d],
              ["Presupuestos 30 días", s.marketplace.quotes_30d],
              ["Presupuestos aceptados 30 días", s.marketplace.quotes_accepted_30d],
              ["Conversaciones 30 días", s.marketplace.conversations_30d],
              ["Conversaciones en total", s.marketplace.conversations_total],
            ]} />
            <Bars title="Solicitudes por día" series={s.series} pick={(d) => d.requests} />
          </Section>

          <Section title="Ferreterías">
            <Tiles items={[["En el mapa", s.stores.on_map], ["Pendientes de revisión", s.stores.pending]]} />
          </Section>

          <Pressable onPress={() => setTable(!table)} style={styles.tableToggle}>
            <Ionicons name={table ? "chevron-up" : "list-outline"} size={16} color={colors.brandPrimary} />
            <Text style={styles.link}>{table ? "Ocultar tabla" : "Ver los datos en tabla"}</Text>
          </Pressable>
          {table ? <DataTable series={s.series} /> : null}
        </>
      ) : !error ? <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} /> : null}
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const styles = useStyles();
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Tiles({ items }: { items: [string, number][] }) {
  const styles = useStyles();
  return (
    <View style={styles.tiles}>
      {items.map(([label, value]) => (
        <View key={label} style={styles.tile}>
          <Text style={styles.tileValue}>{value.toLocaleString("es-ES")}</Text>
          <Text style={styles.tileLabel}>{label}</Text>
        </View>
      ))}
    </View>
  );
}

// Single-series bar chart (one hue, no legend needed): tap a bar to read that day.
function Bars({ title, series, pick, compact }: { title: string; series: Day[]; pick: (d: Day) => number; compact?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const [sel, setSel] = useState<number | null>(null);
  const values = series.map(pick);
  const max = Math.max(1, ...values);
  const total = values.reduce((a, b) => a + b, 0);
  const i = sel ?? values.length - 1;
  const h = compact ? 64 : 96;
  return (
    <View style={[styles.card, compact && { flex: 1 }]}>
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={styles.readout}>
        {fmtDay(series[i].day)}: <Text style={styles.readoutValue}>{values[i]}</Text>
        {compact ? "" : `  ·  30 días: ${total}`}
      </Text>
      <View style={[styles.plot, { height: h }]} accessibilityLabel={`${title}: ${total} en 30 días`}>
        {values.map((v, k) => (
          <Pressable key={series[k].day} onPress={() => setSel(k)} style={styles.barHit} hitSlop={{ top: 8, bottom: 8 }}>
            <View
              style={{
                height: v ? Math.max(3, (v / max) * h) : 1,
                borderTopLeftRadius: v ? 3 : 0,
                borderTopRightRadius: v ? 3 : 0,
                backgroundColor: v ? (k === i ? colors.onSurface : colors.brandPrimary) : colors.border,
              }}
            />
          </Pressable>
        ))}
      </View>
      <View style={styles.axis}>
        <Text style={styles.axisText}>{fmtDay(series[0].day)}</Text>
        <Text style={styles.axisText}>máx. {max}</Text>
        <Text style={styles.axisText}>{fmtDay(series[series.length - 1].day)}</Text>
      </View>
    </View>
  );
}

function Rank({ label, value, max }: { label: string; value: number; max: number }) {
  const styles = useStyles();
  return (
    <View style={styles.rankRow}>
      <Text style={styles.rankLabel}>{label}</Text>
      <View style={styles.rankTrack}>
        <View style={[styles.rankBar, { width: `${Math.max(4, (value / max) * 100)}%` }]} />
      </View>
      <Text style={styles.rankValue}>{value}</Text>
    </View>
  );
}

function DataTable({ series }: { series: Day[] }) {
  const styles = useStyles();
  const cols: [string, (d: Day) => string | number][] = [
    ["Día", (d) => fmtDay(d.day)], ["Activas", (d) => d.active_users], ["Nuevas", (d) => d.new_users],
    ["Diagn.", (d) => d.diagnoses], ["Solic.", (d) => d.requests], ["Grok", (d) => d.ai_grok], ["Gemini", (d) => d.ai_gemini],
  ];
  return (
    <View style={styles.card}>
      <View style={styles.tr}>
        {cols.map(([h]) => <Text key={h} style={[styles.td, styles.th]}>{h}</Text>)}
      </View>
      {[...series].reverse().map((d) => (
        <View key={d.day} style={styles.tr}>
          {cols.map(([h, f]) => <Text key={h} style={styles.td}>{f(d)}</Text>)}
        </View>
      ))}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  center: { alignItems: "center", paddingHorizontal: 16 },
  page: { paddingHorizontal: 16, maxWidth: 760, width: "100%", alignSelf: "center" },
  loginCard: { width: "100%", maxWidth: 380, padding: 20, borderRadius: 18, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 12 },
  title: { color: c.onSurface, fontFamily: fonts.display, fontSize: 24 },
  muted: { color: c.muted, fontSize: 12, lineHeight: 17 },
  input: { minHeight: 48, paddingHorizontal: 12, borderRadius: 10, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface, color: c.onSurface, fontSize: 15 },
  error: { color: c.error, fontSize: 13, fontWeight: "700", marginVertical: 6 },
  header: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
  iconBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceTertiary },
  section: { marginTop: 18, gap: 10 },
  sectionTitle: { color: c.onSurface, fontSize: 17, fontWeight: "800" },
  tiles: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  tile: { flexGrow: 1, flexBasis: "30%", minWidth: 100, padding: 12, borderRadius: 14, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  tileValue: { color: c.onSurface, fontFamily: fonts.display, fontSize: 26 },
  tileLabel: { marginTop: 2, color: c.muted, fontSize: 11, lineHeight: 14 },
  card: { padding: 12, borderRadius: 14, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 6 },
  cardTitle: { color: c.onSurface, fontSize: 13, fontWeight: "800" },
  readout: { color: c.muted, fontSize: 11 },
  readoutValue: { color: c.onSurface, fontWeight: "800" },
  plot: { flexDirection: "row", alignItems: "flex-end", borderBottomWidth: 1, borderBottomColor: c.border },
  barHit: { flex: 1, height: "100%", justifyContent: "flex-end", paddingHorizontal: 1 },
  axis: { flexDirection: "row", justifyContent: "space-between" },
  axisText: { color: c.muted, fontSize: 10 },
  twoCol: { flexDirection: "row", gap: 8 },
  note: { color: c.muted, fontSize: 11, lineHeight: 15 },
  rankRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  rankLabel: { width: 96, color: c.onSurfaceTertiary, fontSize: 12 },
  rankTrack: { flex: 1, height: 10, borderRadius: 5, backgroundColor: c.surfaceTertiary, overflow: "hidden" },
  rankBar: { height: "100%", borderRadius: 5, backgroundColor: c.brandPrimary },
  rankValue: { width: 32, textAlign: "right", color: c.onSurface, fontSize: 12, fontWeight: "700" },
  tableToggle: { marginTop: 20, flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", padding: 4 },
  link: { color: c.brandPrimary, fontSize: 13, fontWeight: "700" },
  tr: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: c.divider, paddingVertical: 5 },
  td: { flex: 1, color: c.onSurfaceTertiary, fontSize: 11, textAlign: "right" },
  th: { color: c.onSurface, fontWeight: "800" },
}));
