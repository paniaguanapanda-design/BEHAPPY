import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useI18n } from "@/src/i18n";
import { Button } from "@/src/ui";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { setProIntent } from "@/src/postLogin";

const HERO = require("@/assets/images/login-hero.jpg");

const BENEFITS = [
  { icon: "camera-outline", title: "pro_b1_t", text: "pro_b1" },
  { icon: "location-outline", title: "pro_b2_t", text: "pro_b2" },
  { icon: "shield-checkmark-outline", title: "pro_b3_t", text: "pro_b3" },
  { icon: "chatbubbles-outline", title: "pro_b4_t", text: "pro_b4" },
] as const;

// Page for specialists, readable before signing in (opened from the login screen).
export default function Pro() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t } = useI18n();

  const backToLogin = () => (router.canGoBack() ? router.back() : router.replace("/login"));
  const start = () => {
    setProIntent(); // the login screen opens in "create account" mode, then the profile form
    backToLogin();
  };

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}>
        <View style={styles.hero}>
          <Image source={HERO} style={styles.fill} contentFit="cover" contentPosition={{ left: "62%", top: "40%" }} />
          <LinearGradient
            colors={["rgba(10,22,40,0.6)", "rgba(10,22,40,0.25)", colors.surfaceInverse]}
            locations={[0, 0.4, 1]}
            style={styles.fill}
          />
          <Pressable
            testID="pro-back"
            onPress={backToLogin}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Back"
            style={[styles.back, { top: insets.top + 8 }]}
          >
            <Ionicons name="arrow-back" size={22} color={colors.onSurfaceInverse} />
          </Pressable>
          <View style={styles.heroBottom}>
            <Text style={styles.title}>{t("pro_title")}</Text>
            <Text style={styles.sub}>{t("pro_sub")}</Text>
          </View>
        </View>

        <View style={styles.body}>
          <View style={styles.benefits}>
            {BENEFITS.map((b) => (
              <View key={b.title} style={styles.benefit}>
                <View style={styles.bIcon}>
                  <Ionicons name={b.icon} size={20} color={colors.onBrandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.bTitle}>{t(b.title)}</Text>
                  <Text style={styles.bText}>{t(b.text)}</Text>
                </View>
              </View>
            ))}
          </View>

          <Text style={styles.h2}>{t("pro_how")}</Text>
          <View style={styles.steps}>
            {(["pro_s1", "pro_s2", "pro_s3"] as const).map((k, i) => (
              <View key={k} style={styles.step}>
                <Text style={styles.stepNum}>{i + 1}</Text>
                <Text style={styles.stepText}>{t(k)}</Text>
              </View>
            ))}
          </View>

          <View style={styles.price}>
            <Text style={styles.priceTitle}>{t("pro_price_t")}</Text>
            <Text style={styles.priceText}>{t("pro_price")}</Text>
            <Text style={styles.prereg}>{t("pro_prereg")}</Text>
          </View>

          <Button testID="pro-start" title={t("pro_cta")} icon="briefcase-outline" onPress={start} />
          <Pressable testID="pro-have-account" onPress={backToLogin} style={styles.link}>
            <Text style={styles.linkText}>{t("pro_have_account")}</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  fill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  hero: { height: 320, justifyContent: "flex-end", overflow: "hidden", backgroundColor: c.surfaceInverse },
  back: {
    position: "absolute",
    left: 12,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: c.scrim,
    alignItems: "center",
    justifyContent: "center",
  },
  heroBottom: { paddingHorizontal: 22, paddingBottom: 22, gap: 8 },
  title: { color: c.onSurfaceInverse, fontSize: 30, fontFamily: fonts.display, letterSpacing: -0.7, lineHeight: 33 },
  sub: { color: c.onSurfaceInverse, opacity: 0.82, fontSize: 15, lineHeight: 21 },
  body: { paddingHorizontal: 20, paddingTop: 20, gap: 14 },
  benefits: { gap: 10 },
  benefit: {
    flexDirection: "row",
    gap: 12,
    alignItems: "center",
    backgroundColor: c.surfaceSecondary,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 18,
    padding: 14,
  },
  bIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  bTitle: { fontSize: 16, fontFamily: fonts.display, color: c.onSurface },
  bText: { fontSize: 14, lineHeight: 19, color: c.muted, marginTop: 2 },
  h2: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface, marginTop: 8 },
  steps: { gap: 10 },
  step: { flexDirection: "row", alignItems: "center", gap: 12 },
  stepNum: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: c.surfaceInverse,
    color: c.onSurfaceInverse,
    textAlign: "center",
    lineHeight: 30,
    fontWeight: "700",
    overflow: "hidden",
  },
  stepText: { flex: 1, fontSize: 15, color: c.onSurface },
  price: { backgroundColor: c.brandSecondary, borderRadius: 18, padding: 16, gap: 4, marginTop: 4 },
  priceTitle: { fontSize: 16, fontFamily: fonts.display, color: c.onSurface },
  priceText: { fontSize: 15, color: c.onSurface },
  prereg: { fontSize: 13, lineHeight: 18, color: c.onBrandSecondary, marginTop: 4 },
  link: { alignItems: "center", paddingVertical: 12, minHeight: 44 },
  linkText: { color: c.brandTertiary, fontWeight: "600", fontSize: 14 },
}));
