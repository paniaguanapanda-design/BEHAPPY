import React, { useEffect } from "react";
import { Text, View } from "react-native";
import { Image } from "expo-image";
import { StatusBar } from "expo-status-bar";
import Animated, {
  Easing,
  FadeInUp,
  ReduceMotion,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withSequence,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { useI18n } from "@/src/i18n";
import { fonts, makeStyles } from "@/src/theme";

const ICON = require("@/assets/images/splash-icon.png");
// Same size and place as the native splash (app.json, imageWidth 200): the hand-off is seamless.
const ICON_SIZE = 200;
const EASE_OUT = Easing.bezier(0.23, 1, 0.32, 1);

const NAME_IN = FadeInUp.duration(350).delay(250).easing(EASE_OUT).reduceMotion(ReduceMotion.System);
const TAGLINE_IN = FadeInUp.duration(350).delay(420).easing(EASE_OUT).reduceMotion(ReduceMotion.System);

export function AppSplash() {
  const styles = useStyles();
  const { t } = useI18n();
  const reduced = useReducedMotion();
  const scale = useSharedValue(1);

  // One happy "hop" of the house, the only flourish of the welcome screen.
  useEffect(() => {
    if (reduced) return;
    scale.set(
      withDelay(
        120,
        withSequence(
          withTiming(1.07, { duration: 180, easing: EASE_OUT }),
          withSpring(1, { duration: 450, dampingRatio: 0.45 }),
        ),
      ),
    );
  }, [reduced, scale]);

  const iconStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.get() }] }));

  return (
    <View style={styles.root} testID="app-splash">
      <StatusBar style="light" />
      <Animated.View style={[styles.icon, iconStyle]}>
        <Image source={ICON} style={styles.iconImg} contentFit="contain" />
      </Animated.View>
      <View style={styles.texts}>
        <Animated.Text entering={NAME_IN} style={styles.name}>
          BeHappy
        </Animated.Text>
        <Animated.View entering={TAGLINE_IN}>
          <Text style={styles.tagline}>{t("splash_tagline")}</Text>
        </Animated.View>
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  // Must match the native splash background (app.json, expo-splash-screen backgroundColor).
  root: { flex: 1, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  icon: { width: ICON_SIZE, height: ICON_SIZE },
  iconImg: { width: "100%", height: "100%" },
  // Below the centered house, so the house never moves when the text appears.
  texts: { position: "absolute", top: "50%", marginTop: ICON_SIZE / 2 + 16, left: 24, right: 24, alignItems: "center", gap: 6 },
  name: { color: c.onSurfaceInverse, fontSize: 40, fontFamily: fonts.display, letterSpacing: -0.8 },
  tagline: { color: "rgba(255,255,255,0.7)", fontSize: 15, textAlign: "center" },
}));
