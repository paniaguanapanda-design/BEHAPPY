import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import type { PurchasesPackage } from "react-native-purchases";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { rcEnabled, rcSimulated, useSubscription } from "@/src/revenuecat";
import { makeStyles, useTheme } from "@/src/theme";
import { Button } from "@/src/ui";
import { fmtDate } from "@/src/time";

import { Plan, useMembership } from "@/src/membership";

export default function MembershipScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const toast = useToast();
  const params = useLocalSearchParams<{ session_id?: string }>();
  const mq = useMembership();
  const sub = useSubscription();
  const [plan, setPlan] = useState<Plan>("yearly");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [pendingSession, setPendingSession] = useState<string | null>(null);
  const [confirmPkg, setConfirmPkg] = useState<PurchasesPackage | null>(null);
  const synced = useRef<string | null>(null);

  const m = mq.data;
  const isSpecialist = !!user?.specialist_id;

  const refreshAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["membership"] });
    queryClient.invalidateQueries({ queryKey: ["specialist-me"] });
    queryClient.invalidateQueries({ queryKey: ["specialists"] });
    queryClient.invalidateQueries({ queryKey: ["specialist"] });
  }, []);

  const pollStatus = useCallback(
    async (sid: string) => {
      setChecking(true);
      try {
        for (let i = 0; i < 8; i++) {
          const r = await api<{ payment_status: string; status: string }>(`/membership/checkout/status/${sid}`);
          if (r.payment_status === "paid") {
            toast(t("mb_paid"));
            setPendingSession(null);
            refreshAll();
            return;
          }
          if (r.status === "expired") break;
          await new Promise((res) => setTimeout(res, 2000));
        }
        toast(t("mb_pending_pay"), "info");
      } catch (e: any) {
        toast(e.message, "error");
      } finally {
        setChecking(false);
      }
    },
    [refreshAll, t, toast],
  );

  // Web: returning from Stripe Checkout
  useEffect(() => {
    if (params.session_id) {
      pollStatus(params.session_id);
      if (Platform.OS === "web") window.history.replaceState(window.history.state, "", window.location.pathname);
    }
  }, [params.session_id, pollStatus]);

  const pkgs = sub.offerings?.current?.availablePackages ?? [];
  const pkgFor = (p: Plan) => pkgs.find((k) => k.identifier === (p === "monthly" ? "$rc_monthly" : "$rc_annual"));

  // Mirror the in-app entitlement to the backend so the specialist becomes visible to clients
  useEffect(() => {
    const ent = sub.entitlement;
    if (!ent || !isSpecialist) return;
    const key = `${ent.productIdentifier}-${ent.expirationDate}`;
    if (synced.current === key) return;
    synced.current = key;
    const annualId = pkgFor("yearly")?.product.identifier;
    const p: Plan = ent.productIdentifier === annualId || /annual|year/i.test(ent.productIdentifier) ? "yearly" : "monthly";
    api("/membership/revenuecat-sync", { body: { plan: p, expiration_date: ent.expirationDate } })
      .then(refreshAll)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sub.entitlement, isSpecialist]);

  const payStripe = async () => {
    setBusy(true);
    try {
      const origin = Platform.OS === "web" ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL as string);
      const r = await api<{ url: string; session_id: string }>("/membership/checkout", { body: { plan, origin_url: origin } });
      if (Platform.OS === "web") {
        window.location.href = r.url;
        return;
      }
      setPendingSession(r.session_id);
      await WebBrowser.openBrowserAsync(r.url);
      await pollStatus(r.session_id);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const doPurchase = async (pkg: PurchasesPackage) => {
    setConfirmPkg(null);
    try {
      await sub.purchase(pkg);
      toast(t("mb_paid"));
    } catch (e: any) {
      if (e?.userCancelled) return;
      toast(e?.message || t("error_generic"), "error");
    }
  };

  const buyInApp = () => {
    const pkg = pkgFor(plan);
    if (!pkg) return toast(t("mb_unavailable"), "error");
    if (rcSimulated) setConfirmPkg(pkg);
    else doPurchase(pkg);
  };

  const restore = async () => {
    try {
      await sub.restore();
      toast(t("saved"));
    } catch (e: any) {
      toast(e?.message || t("error_generic"), "error");
    }
  };

  const price = (p: Plan) => `${(m?.plans?.[p] ?? (p === "monthly" ? 19.99 : 199.99)).toFixed(2).replace(".", ",")} €`;
  const benefits = ["mb_benefit_1", "mb_benefit_2", "mb_benefit_3", "mb_benefit_4"];

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}>
        <LinearGradient colors={[colors.brandPrimary, colors.brandTertiary]} style={[styles.hero, { paddingTop: insets.top + 8 }]}>
          <Pressable testID="membership-back-button" onPress={() => (router.canGoBack() ? router.back() : router.replace("/profile"))} style={styles.back}>
            <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
          </Pressable>
          <View style={styles.crown}>
            <Ionicons name="ribbon" size={30} color={colors.brandPrimary} />
          </View>
          <Text style={styles.heroTitle}>{t("membership_title")}</Text>
          <Text style={styles.heroSub}>{t("membership_sub")}</Text>
        </LinearGradient>

        <View style={styles.content}>
          {mq.isLoading ? (
            <ActivityIndicator color={colors.brandPrimary} />
          ) : (
            <View style={[styles.status, m?.active ? styles.statusOn : styles.statusOff]} testID="membership-status">
              <Ionicons name={m?.active ? "checkmark-circle" : "alert-circle"} size={22} color={m?.active ? colors.success : colors.warning} />
              <View style={{ flex: 1 }}>
                <Text style={styles.statusTitle} testID="membership-status-text">
                  {m?.active ? t("mb_active") : t("mb_inactive")}
                </Text>
                {m?.active && m.expires_at ? (
                  <Text style={styles.statusSub}>
                    {t(m.plan === "yearly" ? "yearly" : "monthly")} · {t("active_until")} {fmtDate(m.expires_at, lang)}
                  </Text>
                ) : null}
              </View>
            </View>
          )}

          {!isSpecialist && (
            <View style={styles.warn}>
              <Text style={styles.warnText}>{t("need_profile_first")}</Text>
              <Button title={t("become_specialist")} onPress={() => router.replace("/specialist-form")} testID="membership-create-profile-button" />
            </View>
          )}

          <View style={styles.benefits}>
            {benefits.map((b) => (
              <View key={b} style={styles.benefit}>
                <Ionicons name="checkmark" size={18} color={colors.brandPrimary} />
                <Text style={styles.benefitText}>{t(b)}</Text>
              </View>
            ))}
          </View>

          <View style={styles.plans}>
            {(["monthly", "yearly"] as Plan[]).map((p) => (
              <Pressable key={p} testID={`plan-${p}`} onPress={() => setPlan(p)} style={[styles.plan, plan === p && styles.planOn]}>
                {p === "yearly" && <Text style={styles.save}>{t("two_months_free")}</Text>}
                <View style={styles.radio}>{plan === p && <View style={styles.radioDot} />}</View>
                <Text style={styles.planName}>{t(p)}</Text>
                <Text style={styles.planPrice} testID={`plan-price-${p}`}>
                  {price(p)}
                </Text>
                <Text style={styles.planPer}>{t(p === "monthly" ? "per_month" : "per_year")}</Text>
              </Pressable>
            ))}
          </View>

          {checking && (
            <View style={styles.checking} testID="membership-checking">
              <ActivityIndicator color={colors.brandPrimary} />
              <Text style={styles.statusSub}>{t("mb_checking")}</Text>
            </View>
          )}

          {(Platform.OS === "web" || __DEV__) && (
          <View style={styles.method}>
            <Button title={t("pay_card")} icon="card" onPress={payStripe} loading={busy} disabled={!isSpecialist || checking} testID="pay-stripe-button" />
            <Text style={styles.methodSub}>{t("pay_card_sub")}</Text>
            {pendingSession && !checking ? (
              <Button variant="ghost" title={t("check_payment")} onPress={() => pollStatus(pendingSession)} testID="check-payment-button" />
            ) : null}
          </View>
          )}

          {rcEnabled && (
            <View style={styles.method}>
              {rcSimulated && (
                <View style={styles.simTag}>
                  <Text style={styles.simText}>{t("simulated")}</Text>
                </View>
              )}
              {sub.identityError ? <Text style={styles.err}>{sub.identityError}</Text> : null}
              {sub.isLoading ? (
                <ActivityIndicator color={colors.brandPrimary} />
              ) : pkgs.length === 0 ? (
                <Text style={styles.methodSub}>{t("mb_unavailable")}</Text>
              ) : (
                <Button
                  variant="secondary"
                  icon="phone-portrait-outline"
                  title={t("pay_inapp")}
                  onPress={buyInApp}
                  loading={sub.isPurchasing}
                  disabled={!isSpecialist || !sub.identityReady}
                  testID="pay-inapp-button"
                />
              )}
              <Text style={styles.methodSub}>{t("pay_inapp_sub")}</Text>
              <Pressable testID="restore-purchases-button" onPress={restore} style={styles.restore} disabled={sub.isRestoring}>
                <Text style={styles.restoreText}>{t("restore")}</Text>
              </Pressable>
            </View>
          )}
        </View>
      </ScrollView>

      <Modal visible={!!confirmPkg} transparent animationType="fade" onRequestClose={() => setConfirmPkg(null)}>
        <View style={styles.backdrop}>
          <View style={styles.dialog} testID="confirm-purchase-modal">
            <Text style={styles.dialogTitle}>{t("confirm_purchase")}</Text>
            <Text style={styles.methodSub}>{t("confirm_purchase_text")}</Text>
            <Text style={styles.planPrice}>{price(plan)}</Text>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button style={{ flex: 1 }} variant="ghost" title={t("cancel")} onPress={() => setConfirmPkg(null)} testID="confirm-purchase-cancel" />
              <Button style={{ flex: 1 }} title={t("confirm")} onPress={() => confirmPkg && doPurchase(confirmPkg)} testID="confirm-purchase-ok" />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  hero: { paddingHorizontal: 24, paddingBottom: 32, alignItems: "center", gap: 8 },
  back: { alignSelf: "flex-start", width: 44, height: 44, alignItems: "center", justifyContent: "center", marginLeft: -12 },
  crown: { width: 64, height: 64, borderRadius: 32, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  heroTitle: { color: c.onBrandPrimary, fontSize: 26, fontWeight: "800", textAlign: "center", letterSpacing: -0.5 },
  heroSub: { color: c.onBrandPrimary, opacity: 0.85, fontSize: 15, textAlign: "center" },
  content: { padding: 16, gap: 16 },
  status: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16, borderRadius: 12, borderWidth: 1 },
  statusOn: { backgroundColor: c.brandSecondary, borderColor: c.brandSecondary },
  statusOff: { backgroundColor: c.surfaceSecondary, borderColor: c.border },
  statusTitle: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  statusSub: { fontSize: 13, color: c.muted, marginTop: 2 },
  warn: { padding: 16, borderRadius: 12, backgroundColor: c.surfaceTertiary, gap: 12 },
  warnText: { color: c.onSurface, fontSize: 14 },
  benefits: { gap: 10, padding: 16, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  benefit: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  benefitText: { flex: 1, fontSize: 15, color: c.onSurface, lineHeight: 21 },
  plans: { flexDirection: "row", gap: 12 },
  plan: { flex: 1, padding: 16, paddingTop: 24, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 2, borderColor: c.border, gap: 4 },
  planOn: { borderColor: c.brandPrimary, backgroundColor: c.brandSecondary },
  save: { position: "absolute", top: -11, right: 12, backgroundColor: c.warning, color: c.onWarning, fontSize: 11, fontWeight: "800", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: c.brandPrimary, alignItems: "center", justifyContent: "center", marginBottom: 6 },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: c.brandPrimary },
  planName: { fontSize: 15, fontWeight: "700", color: c.onSurface },
  planPrice: { fontSize: 24, fontWeight: "800", color: c.onSurface, letterSpacing: -0.5 },
  planPer: { fontSize: 13, color: c.muted },
  checking: { flexDirection: "row", alignItems: "center", gap: 8, justifyContent: "center" },
  method: { gap: 8, padding: 16, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  methodSub: { fontSize: 13, color: c.muted, lineHeight: 18 },
  simTag: { alignSelf: "flex-start", backgroundColor: c.surfaceTertiary, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  simText: { fontSize: 12, fontWeight: "700", color: c.onSurfaceTertiary },
  err: { color: c.error, fontSize: 13 },
  restore: { alignItems: "center", minHeight: 44, justifyContent: "center" },
  restoreText: { color: c.brandTertiary, fontWeight: "700", fontSize: 14 },
  backdrop: { flex: 1, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center", padding: 24 },
  dialog: { width: "100%", maxWidth: 360, backgroundColor: c.surfaceSecondary, borderRadius: 20, padding: 24, gap: 12 },
  dialogTitle: { fontSize: 20, fontWeight: "800", color: c.onSurface },
}));
