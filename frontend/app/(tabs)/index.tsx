import React from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { setPendingScanNote, useDiagnose } from "@/src/useDiagnose";
import { AnalyzingOverlay } from "@/src/AnalyzingOverlay";
import { BouncyIcon, Button } from "@/src/ui";

const HERO = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Ceiling_water_damage.jpg/1280px-Ceiling_water_damage.jpg";

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
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.hello} testID="home-greeting">
          {user?.name ? `${t("hello")}, ${user.name.split(" ")[0]}` : t("hello")}
        </Text>
        <Text style={styles.title}>{t("home_title")}</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ paddingBottom: bottomChrome + 24 }}
      >
        <Animated.View entering={FadeInDown.duration(250)}>
          <Pressable
            testID="scan-problem-button"
            onPress={() => {
              setPendingScanNote(note.trim());
              router.push("/scan");
            }}
            onPressIn={() => setScanPressed(true)}
            onPressOut={() => setScanPressed(false)}
            style={({ pressed }) => [styles.hero, pressed && { transform: [{ scale: 0.98 }] }]}
          >
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
                <BouncyIcon name="camera" size={26} color={colors.onBrandPrimary} active={scanPressed} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.heroTitle}>{t("scan_cta")}</Text>
                <Text style={styles.heroSub}>{t("scan_cta_sub")}</Text>
              </View>
              <Ionicons name="arrow-forward" size={22} color={colors.onSurfaceInverse} />
            </View>
          </Pressable>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(60).duration(250)}>
          <Pressable
            testID="gallery-upload-button"
            onPress={() => pickFromGallery(false, note)}
            onPressIn={() => setGalleryPressed(true)}
            onPressOut={() => setGalleryPressed(false)}
            style={styles.galleryBtn}
          >
            <BouncyIcon name="images-outline" size={20} color={colors.brandPrimary} active={galleryPressed} />
            <Text style={styles.galleryText}>{t("gallery_cta")}</Text>
          </Pressable>
        </Animated.View>

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

const C = 26;
const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 24, paddingBottom: 16, backgroundColor: c.surface },
  hello: { fontSize: 14, color: c.muted, fontWeight: "600" },
  title: { fontSize: 28, fontFamily: fonts.display, color: c.onSurface, letterSpacing: -0.6, marginTop: 4 },
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
  heroTitle: { color: c.onSurfaceInverse, fontSize: 20, fontFamily: fonts.display },
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
  galleryText: { color: c.brandTertiary, fontWeight: "700", fontSize: 15 },
  requestCard: {
    marginHorizontal: 16,
    marginTop: 24,
    padding: 16,
    gap: 12,
    borderRadius: 16,
    backgroundColor: c.surfaceSecondary,
    borderWidth: 1,
    borderColor: c.border,
  },
  requestTitle: { color: c.onSurface, fontSize: 17, fontWeight: "700" },
  requestInput: {
    minHeight: 96,
    maxHeight: 140,
    padding: 12,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 10,
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
