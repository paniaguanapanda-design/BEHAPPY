import React, { useEffect, useRef, useState } from "react";
import Animated, { Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withRepeat, withSequence, withTiming } from "react-native-reanimated";
import { Linking, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { CameraView, useCameraPermissions } from "expo-camera";
import { Image } from "expo-image";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { takePendingScanNote, useDiagnose } from "@/src/useDiagnose";
import { AnalyzingOverlay } from "@/src/AnalyzingOverlay";
import { Button } from "@/src/ui";
import { useToast } from "@/src/toast";

const RETICLE = 270;

// A beam of light sweeping up and down the frame while the camera is live.
function ScanLine({ color }: { color: string }) {
  const y = useSharedValue(0);
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    if (reduceMotion) return;
    y.value = withRepeat(withTiming(RETICLE - 28, { duration: 1500, easing: Easing.inOut(Easing.quad) }), -1, true);
  }, [y, reduceMotion]);
  const style = useAnimatedStyle(() => ({ transform: [{ translateY: y.value }] }));
  return (
    <Animated.View
      style={[
        { position: "absolute", left: 14, right: 14, top: 14, height: 3, borderRadius: 2, backgroundColor: color, shadowColor: color, shadowOpacity: 0.9, shadowRadius: 12, shadowOffset: { width: 0, height: 0 }, elevation: 4 },
        style,
      ]}
    />
  );
}

// The shutter "breathes" so it is obvious where to tap.
function useBreathe() {
  const s = useSharedValue(1);
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    if (reduceMotion) return;
    s.value = withRepeat(withSequence(withTiming(1.06, { duration: 800 }), withTiming(1, { duration: 800 })), -1, false);
  }, [s, reduceMotion]);
  return useAnimatedStyle(() => ({ transform: [{ scale: s.value }] }));
}

export default function Scan() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t } = useI18n();
  const toast = useToast();
  const [perm, requestPerm] = useCameraPermissions();
  const cam = useRef<CameraView>(null);
  const { analyzing, run, pickFromGallery } = useDiagnose();
  const [shot, setShot] = useState<string | null>(null);
  const [note] = useState(takePendingScanNote);
  const showCamera = !shot && !analyzing;
  const breathe = useBreathe();

  const capture = async () => {
    if (analyzing || shot) return;
    try {
      const pic = await cam.current?.takePictureAsync({ quality: 0.7, shutterSound: false });
      if (pic?.uri) {
        setShot(pic.uri); // congela la foto y apaga la camara mientras la IA analiza
        const ok = await run(pic.uri, pic.width, pic.height, true, note);
        if (!ok) setShot(null); // si fallo, vuelve la camara
      }
    } catch (e: any) {
      toast(e?.message || t("error_generic"), "error");
    }
  };

  const close = (
    <Pressable testID="scan-close-button" onPress={() => router.back()} style={[styles.close, { top: insets.top + 8 }]} hitSlop={8}>
      <Ionicons name="close" size={26} color={colors.onSurfaceInverse} />
    </Pressable>
  );

  if (!perm) return <View style={styles.root} />;

  if (!perm.granted) {
    const blocked = !perm.canAskAgain;
    return (
      <View style={[styles.root, styles.permWrap]}>
        {close}
        <ScrollView
          contentContainerStyle={[
            styles.permScroll,
            { paddingTop: insets.top + 64, paddingBottom: insets.bottom + 24 },
          ]}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.permContent}>
            <View style={styles.permIcon}>
              <Ionicons name="camera-outline" size={40} color={colors.onBrandPrimary} />
            </View>
            <Text style={styles.permTitle}>{t("camera_perm_title")}</Text>
            <Text style={styles.permText}>{t("camera_perm_text")}</Text>
            <View style={{ gap: 12, alignSelf: "stretch" }}>
              {blocked ? (
                <Button testID="open-settings-button" title={t("open_settings")} icon="settings-outline" onPress={() => Linking.openSettings()} />
              ) : (
                <Button testID="allow-camera-button" title={t("allow_camera")} icon="camera" onPress={requestPerm} />
              )}
              <Button testID="perm-gallery-button" variant="secondary" title={t("use_gallery")} icon="images-outline" onPress={() => pickFromGallery(true, note)} />
            </View>
          </View>
        </ScrollView>
        <AnalyzingOverlay visible={analyzing} />
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {shot ? (
        <Image source={{ uri: shot }} style={styles.abs} contentFit="cover" />
      ) : showCamera ? (
        <CameraView ref={cam} style={styles.abs} facing="back" />
      ) : null}
      <View style={styles.reticleWrap} pointerEvents="none">
        <View style={styles.reticle}>
          <View style={[styles.corner, styles.tl]} />
          <View style={[styles.corner, styles.tr]} />
          <View style={[styles.corner, styles.bl]} />
          <View style={[styles.corner, styles.br]} />
          {showCamera ? <ScanLine color={colors.sun} /> : null}
        </View>
        <Text style={styles.hint}>{t("frame_hint")}</Text>
      </View>
      {close}
      <View style={[styles.controls, { paddingBottom: insets.bottom + 24 }]}>
        <Pressable testID="scan-gallery-button" onPress={() => pickFromGallery(true, note)} style={styles.side} hitSlop={8}>
          <Ionicons name="images" size={26} color={colors.onSurfaceInverse} />
        </Pressable>
        <Animated.View style={breathe}>
          <Pressable testID="capture-button" accessibilityRole="button" accessibilityLabel={t("scan_cta")} onPress={capture} style={({ pressed }) => [styles.shutter, pressed && { transform: [{ scale: 0.9 }] }]}>
            <View style={styles.shutterInner} />
          </Pressable>
        </Animated.View>
        <View style={styles.side} />
      </View>
      <AnalyzingOverlay visible={analyzing} />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: "#142422" },
  permWrap: { backgroundColor: c.surface, paddingHorizontal: 24, paddingTop: 64 },
  permScroll: { flexGrow: 1, justifyContent: "center" },
  permContent: { width: "100%", maxWidth: 420, alignSelf: "center", gap: 16 },
  abs: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  close: { position: "absolute", left: 16, width: 44, height: 44, borderRadius: 22, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center" },
  reticleWrap: { ...{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }, alignItems: "center", justifyContent: "center", gap: 16 },
  reticle: { width: RETICLE, height: RETICLE },
  corner: { position: "absolute", width: 44, height: 44, borderColor: c.sun },
  tl: { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderTopLeftRadius: 20 },
  tr: { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderTopRightRadius: 20 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4, borderBottomLeftRadius: 20 },
  br: { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4, borderBottomRightRadius: 20 },
  hint: { color: c.onSurfaceInverse, fontSize: 14, fontWeight: "800", backgroundColor: c.scrim, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999, overflow: "hidden" },
  controls: { position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", alignItems: "center", justifyContent: "space-around", paddingTop: 24 },
  side: { width: 52, height: 52, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: c.scrim },
  shutter: { width: 84, height: 84, borderRadius: 42, borderWidth: 5, borderColor: c.onSurfaceInverse, alignItems: "center", justifyContent: "center" },
  shutterInner: { width: 62, height: 62, borderRadius: 31, backgroundColor: c.sun },
  permIcon: { width: 80, height: 80, borderRadius: 40, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  permTitle: { fontSize: 24, fontFamily: fonts.display, color: c.onSurface, textAlign: "center" },
  permText: { fontSize: 15, color: c.muted, textAlign: "center", lineHeight: 22, marginBottom: 16 },
}));
