import React, { useCallback, useEffect, useRef, useState } from "react";
import { AppState, Linking, Modal, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCameraPermissions } from "expo-camera";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";
import { Button } from "@/src/ui";

/** Asks for camera access every time the user enters the app (launch or return from background) until granted. */
export function CameraPermissionPrompt() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { t } = useI18n();
  const [perm, requestPerm, getPerm] = useCameraPermissions();
  const [visible, setVisible] = useState(false);
  const checkedOnLaunch = useRef(false);

  const check = useCallback(async () => {
    const p = await getPerm();
    setVisible(!p.granted);
  }, [getPerm]);

  useEffect(() => {
    if (!checkedOnLaunch.current) {
      checkedOnLaunch.current = true;
      check();
    }
    const sub = AppState.addEventListener("change", (s) => {
      if (s === "active") check();
    });
    return () => sub.remove();
  }, [check]);

  const blocked = perm ? !perm.granted && !perm.canAskAgain : false;

  const allow = async () => {
    if (blocked) {
      Linking.openSettings();
      return;
    }
    const r = await requestPerm();
    if (r.granted) setVisible(false);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={() => setVisible(false)}>
      <Pressable style={styles.backdrop} onPress={() => setVisible(false)} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]} testID="camera-permission-prompt">
        <View style={styles.handle} />
        <View style={styles.icon}>
          <Ionicons name="camera" size={32} color={colors.onBrandPrimary} />
        </View>
        <Text style={styles.title}>{t("camera_perm_title")}</Text>
        <Text style={styles.text}>{blocked ? t("cam_blocked_text") : t("camera_perm_text")}</Text>
        <Button
          title={blocked ? t("open_settings") : t("allow_camera")}
          icon={blocked ? "settings-outline" : "camera"}
          onPress={allow}
          testID="camera-permission-allow-button"
        />
        <Button variant="ghost" title={t("not_now")} onPress={() => setVisible(false)} testID="camera-permission-later-button" />
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((c) => ({
  backdrop: { flex: 1, backgroundColor: c.scrim },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, gap: 12, alignItems: "stretch" },
  handle: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, backgroundColor: c.borderStrong },
  icon: { alignSelf: "center", width: 72, height: 72, borderRadius: 36, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: 8 },
  title: { fontSize: 22, fontWeight: "800", color: c.onSurface, textAlign: "center" },
  text: { fontSize: 15, color: c.muted, textAlign: "center", lineHeight: 22, marginBottom: 8 },
}));
