import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";
import { useDiagnose } from "@/src/useDiagnose";
import { AnalyzingOverlay } from "@/src/AnalyzingOverlay";

const HERO = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Ceiling_water_damage.jpg/1280px-Ceiling_water_damage.jpg";

export default function Home() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useI18n();
  const { analyzing, pickFromGallery } = useDiagnose();

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.hello} testID="home-greeting">
          {t("hello")}, {user?.name?.split(" ")[0]}
        </Text>
        <Text style={styles.title}>{t("home_title")}</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ paddingBottom: bottomChrome + 24 }}
      >
        <Animated.View entering={FadeInDown.duration(400)}>
          <Pressable testID="scan-problem-button" onPress={() => router.push("/scan")} style={({ pressed }) => [styles.hero, pressed && { transform: [{ scale: 0.98 }] }]}>
            <Image source={{ uri: HERO }} style={styles.abs} contentFit="cover" />
            <LinearGradient colors={["transparent", colors.surfaceInverse]} style={styles.abs} />
            <View style={styles.reticle}>
              <View style={[styles.corner, styles.tl]} />
              <View style={[styles.corner, styles.tr]} />
              <View style={[styles.corner, styles.bl]} />
              <View style={[styles.corner, styles.br]} />
            </View>
            <View style={styles.heroContent}>
              <View style={styles.camIcon}>
                <Ionicons name="camera" size={26} color={colors.onBrandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.heroTitle}>{t("scan_cta")}</Text>
                <Text style={styles.heroSub}>{t("scan_cta_sub")}</Text>
              </View>
              <Ionicons name="arrow-forward" size={22} color={colors.onSurfaceInverse} />
            </View>
          </Pressable>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(100).duration(400)}>
          <Pressable testID="gallery-upload-button" onPress={() => pickFromGallery()} style={styles.galleryBtn}>
            <Ionicons name="images-outline" size={20} color={colors.brandPrimary} />
            <Text style={styles.galleryText}>{t("gallery_cta")}</Text>
          </Pressable>
        </Animated.View>

      </ScrollView>
      <AnalyzingOverlay visible={analyzing} />
    </View>
  );
}

const C = 26;
const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 24, paddingBottom: 16, backgroundColor: c.surface },
  hello: { fontSize: 14, color: c.muted, fontWeight: "600" },
  title: { fontSize: 28, fontWeight: "800", color: c.onSurface, letterSpacing: -0.6, marginTop: 4 },
  abs: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  hero: { marginHorizontal: 16, height: 300, borderRadius: 20, overflow: "hidden", justifyContent: "flex-end" },
  reticle: { position: "absolute", top: 40, left: 60, right: 60, bottom: 110 },
  corner: { position: "absolute", width: C, height: C, borderColor: c.onSurfaceInverse },
  tl: { top: 0, left: 0, borderTopWidth: 3, borderLeftWidth: 3, borderTopLeftRadius: 8 },
  tr: { top: 0, right: 0, borderTopWidth: 3, borderRightWidth: 3, borderTopRightRadius: 8 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 3, borderLeftWidth: 3, borderBottomLeftRadius: 8 },
  br: { bottom: 0, right: 0, borderBottomWidth: 3, borderRightWidth: 3, borderBottomRightRadius: 8 },
  heroContent: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16 },
  camIcon: { width: 52, height: 52, borderRadius: 26, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  heroTitle: { color: c.onSurfaceInverse, fontSize: 20, fontWeight: "800" },
  heroSub: { color: c.onSurfaceInverse, opacity: 0.8, fontSize: 13, marginTop: 2 },
  galleryBtn: {
    marginHorizontal: 16,
    marginTop: 12,
    minHeight: 52,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  galleryText: { color: c.brandPrimary, fontWeight: "700", fontSize: 15 },
  section: { fontSize: 20, fontWeight: "700", color: c.onSurface, marginTop: 32, marginBottom: 12, paddingHorizontal: 24 },
  empty: { marginHorizontal: 16, padding: 24, borderRadius: 20, backgroundColor: c.brandSecondary, alignItems: "center", gap: 8 },
  emptyText: { color: c.onBrandSecondary, textAlign: "center", fontSize: 14, lineHeight: 20 },
  row: {
    marginHorizontal: 16,
    marginBottom: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: c.surfaceSecondary,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderColor: c.border,
  },
  thumb: { width: 56, height: 56, borderRadius: 10 },
  thumbEmpty: { backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  rowSub: { fontSize: 13, color: c.muted },
}));
