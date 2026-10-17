import React, { useRef } from "react";
import { Linking, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { CameraView, useCameraPermissions } from "expo-camera";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";
import { useDiagnose } from "@/src/useDiagnose";
import { AnalyzingOverlay } from "@/src/AnalyzingOverlay";
import { Button } from "@/src/ui";
import { useToast } from "@/src/toast";

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

  const capture = async () => {
    try {
      const pic = await cam.current?.takePictureAsync({ base64: true, quality: 0.5 });
      if (pic?.base64) await run(pic.base64, true);
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
      <View style={[styles.root, styles.permWrap, { paddingTop: insets.top + 56, paddingBottom: insets.bottom + 24 }]}>
        {close}
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
          <Button testID="perm-gallery-button" variant="secondary" title={t("use_gallery")} icon="images-outline" onPress={() => pickFromGallery(true)} />
        </View>
        <AnalyzingOverlay visible={analyzing} />
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <CameraView ref={cam} style={styles.abs} facing="back" />
      <View style={styles.reticleWrap} pointerEvents="none">
        <View style={styles.reticle}>
          <View style={[styles.corner, styles.tl]} />
          <View style={[styles.corner, styles.tr]} />
          <View style={[styles.corner, styles.bl]} />
          <View style={[styles.corner, styles.br]} />
        </View>
        <Text style={styles.hint}>{t("frame_hint")}</Text>
      </View>
      {close}
      <View style={[styles.controls, { paddingBottom: insets.bottom + 24 }]}>
        <Pressable testID="scan-gallery-button" onPress={() => pickFromGallery(true)} style={styles.side} hitSlop={8}>
          <Ionicons name="images" size={26} color={colors.onSurfaceInverse} />
        </Pressable>
        <Pressable testID="capture-button" onPress={capture} style={({ pressed }) => [styles.shutter, pressed && { transform: [{ scale: 0.92 }] }]}>
          <View style={styles.shutterInner} />
        </Pressable>
        <View style={styles.side} />
      </View>
      <AnalyzingOverlay visible={analyzing} />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceInverse },
  abs: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  close: { position: "absolute", left: 16, width: 44, height: 44, borderRadius: 22, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center" },
  reticleWrap: { ...{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }, alignItems: "center", justifyContent: "center", gap: 16 },
  reticle: { width: 260, height: 260 },
  corner: { position: "absolute", width: 40, height: 40, borderColor: c.onSurfaceInverse },
  tl: { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderTopLeftRadius: 12 },
  tr: { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderTopRightRadius: 12 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4, borderBottomLeftRadius: 12 },
  br: { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4, borderBottomRightRadius: 12 },
  hint: { color: c.onSurfaceInverse, fontSize: 14, fontWeight: "600", backgroundColor: c.scrim, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999, overflow: "hidden" },
  controls: { position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", alignItems: "center", justifyContent: "space-around", paddingTop: 24 },
  side: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center", backgroundColor: c.scrim },
  shutter: { width: 80, height: 80, borderRadius: 40, borderWidth: 4, borderColor: c.onSurfaceInverse, alignItems: "center", justifyContent: "center" },
  shutterInner: { width: 62, height: 62, borderRadius: 31, backgroundColor: c.onSurfaceInverse },
  permWrap: { alignItems: "center", paddingHorizontal: 24, gap: 16, backgroundColor: c.surface, justifyContent: "center" },
  permIcon: { width: 80, height: 80, borderRadius: 40, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  permTitle: { fontSize: 24, fontWeight: "800", color: c.onSurface, textAlign: "center" },
  permText: { fontSize: 15, color: c.muted, textAlign: "center", lineHeight: 22, marginBottom: 16 },
}));
