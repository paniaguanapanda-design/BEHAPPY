import React, { useEffect } from "react";
import { View } from "react-native";
import { Image } from "expo-image";
import { StatusBar } from "expo-status-bar";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import Animated, {
  Easing,
  FadeIn,
  FadeInUp,
  ReduceMotion,
  type SharedValue,
  interpolate,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withSequence,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { useI18n } from "@/src/i18n";
import { fonts, makeStyles, useTheme } from "@/src/theme";

const ICON = require("@/assets/images/splash-icon.png");
const BG = require("@/assets/images/splash-bg.jpg"); // navy, lighter in the middle
const GLOW = require("@/assets/images/splash-glow.png"); // soft orange light behind the house
// Same size and place as the native splash (app.json, imageWidth 200): the hand-off is seamless.
const ICON_SIZE = 200;
const FRAME = 252; // viewfinder around the house
const EASE_OUT = Easing.bezier(0.23, 1, 0.32, 1);
const EASE_IN_OUT = Easing.bezier(0.77, 0, 0.175, 1);

// Timeline (ms) - everything lands inside the 1.6 s the welcome screen stays up.
const T_CORNERS = 0; // camera corners close in on the house
const T_SCAN = 380; // a scan line sweeps it
const T_HAPPY = 820; // the house hops and wiggles, sparkles burst
const T_NAME = 900; // "BeHappy" letter by letter
const T_TAGLINE = 1180;

const NAME = "BeHappy".split("");
const SPARKS = [
  { x: -128, y: -96, size: 22, d: 0 },
  { x: 120, y: -112, size: 18, d: 60 },
  { x: 140, y: 10, size: 24, d: 120 },
  { x: -144, y: 26, size: 16, d: 90 },
  { x: -86, y: -150, size: 14, d: 150 },
  { x: 70, y: -156, size: 16, d: 30 },
];

export function AppSplash() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const reduced = useReducedMotion();

  const corners = useSharedValue(reduced ? 1 : 0); // 0 = far out at the screen edges, 1 = locked on
  const scan = useSharedValue(0); // 0 top -> 1 bottom
  const hop = useSharedValue(1);
  const wiggle = useSharedValue(0);
  const spark = useSharedValue(0);
  const bg = useSharedValue(reduced ? 1 : 0);
  const glow = useSharedValue(reduced ? 0.7 : 0);

  useEffect(() => {
    if (reduced) return;
    // The native splash is flat navy: the light fades in so the hand-off has no jump.
    bg.set(withTiming(1, { duration: 300, easing: EASE_OUT }));
    glow.set(
      withSequence(
        withTiming(0.45, { duration: 400, easing: EASE_OUT }),
        withDelay(T_HAPPY - 400, withTiming(1, { duration: 160, easing: EASE_OUT })),
        withTiming(0.7, { duration: 500, easing: EASE_OUT }),
      ),
    );
    corners.set(withDelay(T_CORNERS, withTiming(1, { duration: 420, easing: EASE_OUT })));
    scan.set(withDelay(T_SCAN, withTiming(1, { duration: 420, easing: EASE_IN_OUT })));
    hop.set(
      withDelay(
        T_HAPPY,
        withSequence(withTiming(1.1, { duration: 160, easing: EASE_OUT }), withSpring(1, { duration: 500, dampingRatio: 0.4 })),
      ),
    );
    wiggle.set(
      withDelay(
        T_HAPPY,
        withSequence(
          withTiming(-6, { duration: 90 }),
          withTiming(6, { duration: 110 }),
          withTiming(-3, { duration: 100 }),
          withTiming(0, { duration: 120, easing: EASE_OUT }),
        ),
      ),
    );
    spark.set(withDelay(T_HAPPY, withTiming(1, { duration: 650, easing: Easing.linear })));
  }, [reduced, corners, scan, hop, wiggle, spark, bg, glow]);

  const bgStyle = useAnimatedStyle(() => ({ opacity: bg.get() }));
  const glowStyle = useAnimatedStyle(() => ({ opacity: glow.get(), transform: [{ scale: 0.9 + glow.get() * 0.15 }] }));
  const houseStyle = useAnimatedStyle(() => ({
    transform: [{ scale: hop.get() }, { rotate: `${wiggle.get()}deg` }],
  }));
  const scanStyle = useAnimatedStyle(() => ({
    opacity: scan.get() === 0 || scan.get() === 1 ? 0 : 1,
    transform: [{ translateY: interpolate(scan.get(), [0, 1], [-FRAME / 2 + 8, FRAME / 2 - 8]) }],
  }));

  return (
    <View style={styles.root} testID="app-splash">
      <StatusBar style="light" />
      <Animated.View pointerEvents="none" style={[styles.fill, bgStyle]}>
        <Image source={BG} style={styles.fill} contentFit="cover" />
      </Animated.View>

      <View style={styles.stage}>
        <Animated.View pointerEvents="none" style={[styles.glow, glowStyle]}>
          <Image source={GLOW} style={styles.fill} contentFit="contain" />
        </Animated.View>
        {(["tl", "tr", "bl", "br"] as const).map((pos) => (
          <Corner key={pos} pos={pos} progress={corners} color={colors.sun} />
        ))}

        <Animated.View style={[styles.house, houseStyle]}>
          <Image source={ICON} style={styles.houseImg} contentFit="contain" />
        </Animated.View>

        <Animated.View pointerEvents="none" style={[styles.scan, { backgroundColor: colors.sun, shadowColor: colors.sun }, scanStyle]} />

        {!reduced && SPARKS.map((s, i) => <Spark key={i} {...s} progress={spark} color={colors.sun} />)}
      </View>

      <View style={styles.texts}>
        <View style={styles.nameRow} accessible accessibilityLabel="BeHappy">
          {NAME.map((ch, i) => (
            <Animated.Text
              key={i}
              entering={FadeInUp.duration(320).delay(T_NAME + i * 40).easing(EASE_OUT).reduceMotion(ReduceMotion.System)}
              style={styles.name}
            >
              {ch}
            </Animated.Text>
          ))}
        </View>
        <Animated.Text entering={FadeIn.duration(320).delay(T_TAGLINE)} style={styles.tagline}>
          {t("splash_tagline")}
        </Animated.Text>
      </View>
    </View>
  );
}

// One L-shaped corner of the camera viewfinder: starts near the screen edge, closes in on the house.
function Corner({ pos, progress, color }: { pos: "tl" | "tr" | "bl" | "br"; progress: SharedValue<number>; color: string }) {
  const styles = useStyles();
  const dx = pos === "tl" || pos === "bl" ? -1 : 1;
  const dy = pos === "tl" || pos === "tr" ? -1 : 1;
  const style = useAnimatedStyle(() => {
    const away = interpolate(progress.get(), [0, 1], [140, 0]);
    return {
      opacity: interpolate(progress.get(), [0, 0.35, 1], [0, 1, 1]),
      transform: [{ translateX: dx * away }, { translateY: dy * away }],
    };
  });
  return (
    <Animated.View
      style={[
        styles.corner,
        { borderColor: color },
        pos === "tl" && { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4 },
        pos === "tr" && { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4 },
        pos === "bl" && { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4 },
        pos === "br" && { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4 },
        style,
      ]}
    />
  );
}

// A sparkle that pops out from the house, twinkles and fades.
function Spark({ x, y, size, d, progress, color }: { x: number; y: number; size: number; d: number; progress: SharedValue<number>; color: string }) {
  const styles = useStyles();
  const start = d / 650;
  const style = useAnimatedStyle(() => {
    const p = progress.get();
    const local = Math.min(1, Math.max(0, (p - start) / (1 - start)));
    return {
      opacity: interpolate(local, [0, 0.15, 0.7, 1], [0, 1, 1, 0]),
      transform: [
        { translateX: interpolate(local, [0, 1], [x * 0.55, x]) },
        { translateY: interpolate(local, [0, 1], [y * 0.55, y]) },
        { scale: interpolate(local, [0, 0.3, 1], [0.3, 1.15, 0.8]) },
        { rotate: `${interpolate(local, [0, 1], [0, 45])}deg` },
      ],
    };
  });
  return (
    <Animated.View pointerEvents="none" style={[styles.spark, style]}>
      <Ionicons name="sparkles" size={size} color={color} />
    </Animated.View>
  );
}

const useStyles = makeStyles((c) => ({
  // Must match the native splash background (app.json, expo-splash-screen backgroundColor).
  root: { flex: 1, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  fill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  glow: { position: "absolute", width: 420, height: 420, left: (FRAME - 420) / 2, top: (FRAME - 420) / 2 },
  stage: { width: FRAME, height: FRAME, alignItems: "center", justifyContent: "center" },
  house: { width: ICON_SIZE, height: ICON_SIZE },
  houseImg: { width: "100%", height: "100%" },
  corner: { position: "absolute", width: 40, height: 40 },
  scan: {
    position: "absolute",
    left: 10,
    right: 10,
    height: 3,
    borderRadius: 2,
    shadowOpacity: 0.9,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 6,
  },
  spark: { position: "absolute" },
  // Below the centered stage, so the house never moves when the text appears.
  texts: { position: "absolute", top: "50%", marginTop: FRAME / 2 + 14, left: 24, right: 24, alignItems: "center", gap: 6 },
  nameRow: { flexDirection: "row" },
  name: { color: c.onSurfaceInverse, fontSize: 42, fontFamily: fonts.display, letterSpacing: -0.6 },
  tagline: { color: "rgba(255,255,255,0.72)", fontSize: 15, textAlign: "center" },
}));
