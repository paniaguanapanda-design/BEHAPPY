import React, { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { Button } from "@/src/ui";
import { markSeen } from "@/src/seen";
import { useSubscription } from "@/src/revenuecat";
import { fmtDate } from "@/src/time";

// Google Play one-time products (create them in Play Console and add them to the RevenueCat offering "featured").
const PLANS = [
  { key: "7", product: "featured_7", fallback: "4,99 €", title: "featured_7_title", sub: "featured_7_sub" },
  { key: "30", product: "featured_30", fallback: "14,99 €", title: "featured_30_title", sub: "featured_30_sub" },
] as const;

export default function ProFeatured() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, lang } = useI18n();
  const toast = useToast();
  const sub = useSubscription();
  const status = useQuery({ queryKey: ["featured-status"], queryFn: () => api<any>("/featured/status") });
  const [plan, setPlan] = useState<"7" | "30">("7");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    markSeen("pro_featured");
  }, []);

  const pkgs = (sub.offerings as any)?.all?.featured?.availablePackages || [];
  const pkgFor = (product: string) => pkgs.find((p: any) => p.product?.identifier?.startsWith(product));
  const price = (p: (typeof PLANS)[number]) => pkgFor(p.product)?.product?.priceString || p.fallback;
  const chosen = PLANS.find((p) => p.key === plan)!;
  const s = status.data;
  const trade = t(`pro_cats_${s?.category || "plumbing"}`);

  const buy = async () => {
    if (!s?.membership_active) return router.push("/membership");
    const pkg = pkgFor(chosen.product);
    if (!pkg) return toast(t("featured_unavailable"), "error");
    setBusy(true);
    try {
      await sub.purchase(pkg);
      await api("/featured/sync", { method: "POST" });
      queryClient.invalidateQueries({ queryKey: ["featured-status"] });
      queryClient.invalidateQueries({ queryKey: ["pro-settings"] });
      queryClient.invalidateQueries({ queryKey: ["specialists"] });
      toast(t("featured_done"));
      router.back();
    } catch (e: any) {
      if (!e?.userCancelled) toast(e?.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  const full = s && !s.featured_until && s.slots_left === 0;

  return (
    <View style={styles.root}>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="featured-back" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("featured_short")}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        <View style={[styles.card, styles.hero]}>
          <Text style={styles.star}>⭐</Text>
          <Text style={styles.h2}>{t("featured_hero")}</Text>
          <Text style={styles.heroText}>{t("featured_hero_text").replace("{trade}", trade)}</Text>
        </View>
        {s?.featured_until ? (
          <View style={styles.active}>
            <Ionicons name="checkmark-circle" size={18} color="#16794A" />
            <Text style={styles.activeText}>
              {t("featured_until")} {fmtDate(s.featured_until, lang)}
            </Text>
          </View>
        ) : null}
        {PLANS.map((p) => (
          <Pressable key={p.key} testID={`featured-plan-${p.key}`} onPress={() => setPlan(p.key)} style={[styles.plan, plan === p.key && styles.planOn]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.planTitle}>{t(p.title)}</Text>
              <Text style={styles.planSub}>{t(p.sub)}</Text>
            </View>
            <Text style={styles.planPrice}>{price(p)}</Text>
          </Pressable>
        ))}
        <Text style={styles.small}>{full ? t("featured_full") : t("featured_rules")}</Text>
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + 12 }]}>
        <Button
          testID="featured-buy"
          title={
            s && !s.membership_active
              ? t("activate_membership")
              : `${s?.featured_until ? t("featured_extend") : t("featured_cta")} · ${price(chosen)}`
          }
          onPress={buy}
          loading={busy}
          disabled={!!full || status.isLoading}
        />
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  top: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 4 },
  back: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  body: { padding: 16, gap: 14 },
  card: { backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 18, padding: 14 },
  hero: { alignItems: "center", paddingVertical: 20, gap: 6 },
  star: { fontSize: 40 },
  h2: { fontSize: 18, fontFamily: fonts.display, color: c.onSurface },
  heroText: { fontSize: 14, lineHeight: 20, color: c.onSurfaceTertiary, textAlign: "center" },
  active: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#E7F6EC", borderRadius: 12, padding: 12 },
  activeText: { color: "#16794A", fontWeight: "700", fontSize: 14 },
  plan: { flexDirection: "row", alignItems: "center", borderWidth: 2, borderColor: c.border, borderRadius: 16, padding: 14, backgroundColor: c.surfaceSecondary },
  planOn: { borderColor: c.brandPrimary, backgroundColor: c.brandSecondary },
  planTitle: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  planSub: { fontSize: 13, color: c.muted },
  planPrice: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  small: { fontSize: 12, color: c.muted, textAlign: "center", lineHeight: 17 },
  footer: { paddingHorizontal: 16, paddingTop: 8 },
}));
