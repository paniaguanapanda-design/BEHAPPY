import React from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { setPendingScanNote, useDiagnose } from "@/src/useDiagnose";
import { AnalyzingOverlay } from "@/src/AnalyzingOverlay";
import { InstallPrompt } from "@/src/InstallPrompt";
import { BouncyIcon, Button } from "@/src/ui";

export default function Home() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useI18n();
  const { analyzing, pickFromGallery, run } = useDiagnose();
  const [note, setNote] = React.useState("");
  const [scanPressed, setScanPressed] = React.useState(false);
  const [galleryPressed, setGalleryPressed] = React.useState(false);

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: bottomChrome + 24 }}>
        <View style={[styles.header, { paddingTop: insets.top + 14 }]}>
          <View style={styles.headerRow}>
            <View style={styles.logo}>
              <Image source={require("@/assets/images/logo-house-sun.png")} style={styles.logoImg} contentFit="contain" accessibilityLabel="BE HAPPY" />
              <Text style={styles.logoText}>BeHappy</Text>
            </View>
            <View style={styles.helloChip}>
              <Text style={styles.hello} testID="home-greeting" numberOfLines={1}>
                {user?.name ? `${t("hello")}, ${user.name.split(" ")[0]}` : t("hello")}
              </Text>
            </View>
          </View>
          <Text style={styles.title}>{t("home_calm")}</Text>
          <Text style={styles.subtitle}>{t("home_title")}</Text>
        </View>

        <Animated.View entering={FadeInDown.duration(300)} style={styles.lift}>
          <Pressable
            testID="scan-problem-button"
            onPress={() => {
              setPendingScanNote(note.trim());
              router.push("/scan");
            }}
            onPressIn={() => setScanPressed(true)}
            onPressOut={() => setScanPressed(false)}
            style={({ pressed }) => [styles.hero, pressed && { transform: [{ scale: 0.97 }] }]}
          >
            <View style={styles.camIcon}>
              <BouncyIcon name="camera" size={28} color={colors.brandPrimary} active={scanPressed} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.heroTitle}>{t("scan_cta")}</Text>
              <Text style={styles.heroSub}>{t("scan_cta_sub")}</Text>
            </View>
            <Ionicons name="arrow-forward" size={22} color={colors.onSun} />
          </Pressable>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(60).duration(300)}>
          <Pressable
            testID="gallery-upload-button"
            onPress={() => pickFromGallery(false, note)}
            onPressIn={() => setGalleryPressed(true)}
            onPressOut={() => setGalleryPressed(false)}
            style={({ pressed }) => [styles.galleryBtn, pressed && { transform: [{ scale: 0.98 }] }]}
          >
            <BouncyIcon name="images-outline" size={20} color={colors.brandPrimary} active={galleryPressed} />
            <Text style={styles.galleryText}>{t("gallery_cta")}</Text>
          </Pressable>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(120).duration(300)} style={styles.shortcuts}>
          <Pressable testID="home-stores-shortcut" onPress={() => router.push("/stores")} style={({ pressed }) => [styles.shortcut, pressed && { transform: [{ scale: 0.97 }] }]}>
            <View style={styles.shortcutIcon}>
              <Ionicons name="storefront-outline" size={22} color={colors.brandPrimary} />
            </View>
            <Text style={styles.shortcutText} numberOfLines={2}>{t("stores_title")}</Text>
          </Pressable>
          <Pressable testID="home-requests-shortcut" onPress={() => router.push("/requests")} style={({ pressed }) => [styles.shortcut, pressed && { transform: [{ scale: 0.97 }] }]}>
            <View style={styles.shortcutIcon}>
              <Ionicons name="document-text-outline" size={22} color={colors.brandPrimary} />
            </View>
            <Text style={styles.shortcutText} numberOfLines={2}>{t("my_requests")}</Text>
          </Pressable>
        </Animated.View>

        <View style={styles.install}>
          <InstallPrompt />
        </View>

        <View style={styles.requestCard}>
          <Text style={styles.requestTitle}>{t("request_note_title")}</Text>
          <TextInput
            testID="home-request-input"
            style={styles.requestInput}
            multiline
            maxLength={500}
            placeholder={t("request_note_placeholder")}
            placeholderTextColor={colors.muted}
            value={note}
            onChangeText={setNote}
            textAlignVertical="top"
          />
          {note.trim() ? (
            <Button
              testID="home-text-only-request-button"
              title={t("request_without_photo")}
              icon="people-outline"
              onPress={() => {
                void run(null, undefined, undefined, false, note);
              }}
            />
          ) : null}
        </View>

      </ScrollView>
      <AnalyzingOverlay visible={analyzing} />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: {
    paddingHorizontal: 22,
    paddingBottom: 72,
    backgroundColor: c.surfaceInverse,
    borderBottomLeftRadius: 36,
    borderBottomRightRadius: 36,
    gap: 6,
  },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 14, gap: 12 },
  logo: { flexDirection: "row", alignItems: "center", gap: 8 },
  logoImg: { width: 34, height: 34 },
  logoText: { color: c.onSurfaceInverse, fontFamily: fonts.display, fontSize: 22 },
  helloChip: { backgroundColor: "rgba(255,255,255,0.14)", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, flexShrink: 1 },
  hello: { fontSize: 13, color: c.onSurfaceInverse, fontWeight: "700" },
  title: { fontSize: 30, lineHeight: 34, fontFamily: fonts.displayMedium, color: c.onSurfaceInverse },
  subtitle: { fontSize: 15, color: "rgba(255,255,255,0.82)", fontWeight: "600" },
  lift: { marginTop: -48 },
  hero: {
    marginHorizontal: 16,
    minHeight: 104,
    borderRadius: 28,
    padding: 18,
    backgroundColor: c.sun,
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    shadowColor: "#000",
    shadowOpacity: 0.14,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 8,
  },
  camIcon: { width: 58, height: 58, borderRadius: 29, backgroundColor: c.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  heroTitle: { color: c.onSun, fontSize: 20, fontFamily: fonts.displayMedium },
  heroSub: { color: c.onSun, fontSize: 14, fontWeight: "600", marginTop: 2 },
  galleryBtn: {
    marginHorizontal: 16,
    marginTop: 12,
    minHeight: 52,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: c.borderStrong,
    backgroundColor: c.surfaceSecondary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  galleryText: { color: c.brandPrimary, fontWeight: "800", fontSize: 15 },
  install: { marginHorizontal: 16, marginTop: 16 },
  shortcuts: { flexDirection: "row", gap: 12, marginHorizontal: 16, marginTop: 16 },
  shortcut: {
    flex: 1,
    minHeight: 64,
    borderRadius: 22,
    padding: 12,
    backgroundColor: c.surfaceSecondary,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  shortcutIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  shortcutText: { flex: 1, color: c.onSurface, fontWeight: "800", fontSize: 14 },
  requestCard: {
    marginHorizontal: 16,
    marginTop: 16,
    padding: 16,
    gap: 12,
    borderRadius: 24,
    backgroundColor: c.surfaceSecondary,
    borderWidth: 1,
    borderColor: c.border,
  },
  requestTitle: { color: c.onSurface, fontSize: 18, fontFamily: fonts.displayMedium },
  requestInput: {
    minHeight: 96,
    maxHeight: 140,
    padding: 12,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 16,
    backgroundColor: c.surface,
    color: c.onSurface,
    fontSize: 14,
  },
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
