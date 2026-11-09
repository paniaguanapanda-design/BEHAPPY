import React, { useEffect } from "react";
import { Modal, Text, View } from "react-native";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import Animated, { Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withRepeat, withSequence, withTiming } from "react-native-reanimated";
import { useI18n } from "@/src/i18n";
import { fonts, makeStyles, useTheme } from "@/src/theme";

// While the AI looks at the photo: a sunny face that bobs, with a halo spreading out behind it.
export function AnalyzingOverlay({ visible }: { visible: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const reduceMotion = useReducedMotion();
  const halo = useSharedValue(0);
  const bob = useSharedValue(0);
  useEffect(() => {
    if (!visible || reduceMotion) return;
    halo.value = 0;
    halo.value = withRepeat(withTiming(1, { duration: 1400, easing: Easing.out(Easing.quad) }), -1, false);
    bob.value = withRepeat(withSequence(withTiming(-6, { duration: 500 }), withTiming(0, { duration: 500 })), -1, false);
  }, [visible, reduceMotion, halo, bob]);
  const haloStyle = useAnimatedStyle(() => ({ opacity: 0.5 * (1 - halo.value), transform: [{ scale: 1 + 0.8 * halo.value }] }));
  const faceStyle = useAnimatedStyle(() => ({ transform: [{ translateY: bob.value }] }));
  return (
    <Modal visible={visible} transparent animationType="fade">
      <View style={styles.backdrop} testID="analyzing-overlay">
        <View style={styles.card}>
          <View style={styles.faceWrap}>
            <Animated.View style={[styles.halo, { backgroundColor: colors.sun }, haloStyle]} />
            <Animated.View style={[styles.face, { backgroundColor: colors.sun }, faceStyle]}>
              <Ionicons name="happy-outline" size={52} color={colors.onSun} />
            </Animated.View>
          </View>
          <Text style={styles.title}>{t("analyzing")}</Text>
          <Text style={styles.sub}>{t("analyzing_sub")}</Text>
        </View>
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((c) => ({
  backdrop: { flex: 1, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center", padding: 24 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 28, padding: 32, alignItems: "center", gap: 12, width: "100%", maxWidth: 340 },
  faceWrap: { width: 96, height: 96, alignItems: "center", justifyContent: "center", marginBottom: 6 },
  halo: { position: "absolute", width: 96, height: 96, borderRadius: 48 },
  face: { width: 88, height: 88, borderRadius: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, fontFamily: fonts.display, color: c.onSurface },
  sub: { fontSize: 14, color: c.muted, textAlign: "center" },
}));
