// Animated bottom bars.
// Clients: a floating teal pill with a sunny "scan" button in the middle; the active-tab pill stretches like rubber
// (its leading edge springs fast, the trailing edge follows) and the icon pops.
// Specialists ("Zona Pro"): a dark bar where a beam of light slides to the active tab and lights its icon.
import React, { useEffect, useState } from "react";
import { LayoutChangeEvent, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { Tabs, useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { fonts, pro, useTheme } from "@/src/theme";

type TabBarProps = Parameters<NonNullable<React.ComponentProps<typeof Tabs>["tabBar"]>>[0];
type IconName = React.ComponentProps<typeof Ionicons>["name"];
type Item = { name: string; label: string; on: IconName; off: IconName };

const tap = () => {
  if (Platform.OS !== "web") void Haptics.selectionAsync().catch(() => {});
};

function useTabPress({ state, navigation }: TabBarProps) {
  return (name: string) => {
    const route = state.routes.find((r) => r.name === name);
    if (!route) return;
    const focused = state.routes[state.index]?.key === route.key;
    const event = navigation.emit({ type: "tabPress", target: route.key, canPreventDefault: true });
    tap();
    if (!focused && !event.defaultPrevented) navigation.navigate(route.name, route.params);
  };
}

export function AppTabBar(props: TabBarProps) {
  const { user } = useAuth();
  const isPro = user?.role === "specialist" && !!user.specialist_id;
  return isPro ? <ProTabBar {...props} /> : <ClientTabBar {...props} />;
}

/* ------------------------------ Clients (B) ------------------------------ */

const SLOT_COUNT = 5; // 4 tabs + the scan button in the middle
const TAB_SLOTS = [0, 1, 3, 4];
const PILL_INSET = 6;

function ClientTabBar(props: TabBarProps) {
  const { state, descriptors, insets } = props;
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  const press = useTabPress(props);
  const reduceMotion = useReducedMotion();
  const [width, setWidth] = useState(0);

  const items: Item[] = [
    { name: "index", label: t("tab_home"), on: "home", off: "home-outline" },
    { name: "specialists", label: t("tab_specialists"), on: "people", off: "people-outline" },
    { name: "messages", label: t("tab_messages"), on: "chatbubbles", off: "chatbubbles-outline" },
    { name: "profile", label: t("tab_profile"), on: "person-circle", off: "person-circle-outline" },
  ];
  const activeName = state.routes[state.index]?.name;
  const activeIdx = items.findIndex((i) => i.name === activeName);

  const slotW = width / SLOT_COUNT;
  const left = useSharedValue(0);
  const right = useSharedValue(0);
  const shown = useSharedValue(0);
  const prevIdx = React.useRef(-1);

  useEffect(() => {
    if (!width) return;
    if (activeIdx < 0) {
      shown.value = withTiming(0, { duration: 180 });
      return;
    }
    const slot = TAB_SLOTS[activeIdx];
    const l = slot * slotW + PILL_INSET;
    const r = width - (slot + 1) * slotW + PILL_INSET;
    const first = prevIdx.current < 0;
    const goingRight = !first && TAB_SLOTS[prevIdx.current] < slot;
    prevIdx.current = activeIdx;
    shown.value = withTiming(1, { duration: 200 });
    if (first || reduceMotion) {
      left.value = l;
      right.value = r;
      return;
    }
    const lead = { damping: 15, stiffness: 320, mass: 0.7 };
    const trail = { damping: 14, stiffness: 140, mass: 0.9 };
    left.value = withSpring(l, goingRight ? trail : lead);
    right.value = withSpring(r, goingRight ? lead : trail);
  }, [activeIdx, width, slotW, left, right, shown, reduceMotion]);

  const pillStyle = useAnimatedStyle(() => ({ left: left.value, right: right.value, opacity: shown.value }));

  return (
    <View style={[styles.clientWrap, { backgroundColor: colors.surface, paddingBottom: Math.max(insets.bottom, 10) + 4 }]}>
      <View
        style={[styles.clientBar, { backgroundColor: colors.surfaceInverse }]}
        onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}
        accessibilityRole="tablist"
      >
        {width > 0 && <Animated.View style={[styles.pill, { backgroundColor: colors.sun }, pillStyle]} />}
        {items.map((it, i) => {
          const route = state.routes.find((r) => r.name === it.name);
          const opts = route ? descriptors[route.key]?.options : undefined;
          const focused = i === activeIdx;
          return (
            <Pressable
              key={it.name}
              testID={opts?.tabBarButtonTestID}
              accessibilityRole="tab"
              accessibilityState={{ selected: focused }}
              accessibilityLabel={it.label}
              onPress={() => press(it.name)}
              style={[styles.clientSlot, { left: `${(TAB_SLOTS[i] / SLOT_COUNT) * 100}%`, width: `${100 / SLOT_COUNT}%` }]}
            >
              <PopIcon name={focused ? it.on : it.off} focused={focused} color={focused ? colors.onSun : colors.brandSecondary} />
            </Pressable>
          );
        })}
        <ScanButton
          label={t("scan_cta")}
          onPress={() => {
            tap();
            router.push("/scan");
          }}
        />
      </View>
    </View>
  );
}

function PopIcon({ name, focused, color }: { name: IconName; focused: boolean; color: string }) {
  const scale = useSharedValue(1);
  const rot = useSharedValue(0);
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    if (!focused || reduceMotion) return;
    scale.value = withSequence(withSpring(1.35, { damping: 6, stiffness: 420 }), withSpring(1, { damping: 9, stiffness: 260 }));
    rot.value = withSequence(withTiming(-10, { duration: 120 }), withSpring(0, { damping: 6, stiffness: 300 }));
  }, [focused, reduceMotion, rot, scale]);
  const style = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }, { rotate: `${rot.value}deg` }] }));
  return (
    <Animated.View style={style}>
      <Ionicons name={name} size={24} color={color} />
    </Animated.View>
  );
}

function ScanButton({ label, onPress }: { label: string; onPress: () => void }) {
  const { colors } = useTheme();
  const reduceMotion = useReducedMotion();
  const halo = useSharedValue(0);
  const spin = useSharedValue(0);
  const press = useSharedValue(1);
  useEffect(() => {
    if (reduceMotion) return;
    halo.value = withRepeat(withTiming(1, { duration: 1800, easing: Easing.out(Easing.quad) }), -1, false);
    spin.value = withRepeat(withTiming(360, { duration: 9000, easing: Easing.linear }), -1, false);
  }, [halo, spin, reduceMotion]);
  const haloStyle = useAnimatedStyle(() => ({ opacity: 0.55 * (1 - halo.value), transform: [{ scale: 1 + 0.7 * halo.value }] }));
  const ringStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value}deg` }] }));
  const btnStyle = useAnimatedStyle(() => ({ transform: [{ scale: press.value }] }));
  return (
    <View style={styles.scanSlot} pointerEvents="box-none">
      <Animated.View pointerEvents="none" style={[styles.scanHalo, { backgroundColor: colors.sun }, haloStyle]} />
      <Animated.View pointerEvents="none" style={[styles.scanRing, { borderColor: colors.sun }, ringStyle]} />
      <Animated.View style={btnStyle}>
        <Pressable
          testID="tab-scan"
          accessibilityRole="button"
          accessibilityLabel={label}
          onPress={onPress}
          onPressIn={() => press.set(withSpring(0.9, { damping: 12, stiffness: 400 }))}
          onPressOut={() => press.set(withSpring(1, { damping: 7, stiffness: 300 }))}
          style={[styles.scanBtn, { backgroundColor: colors.sun, borderColor: colors.surface }]}
        >
          <Ionicons name="camera" size={28} color={colors.onSun} />
        </Pressable>
      </Animated.View>
    </View>
  );
}

/* ---------------------------- Specialists (C) ---------------------------- */

function ProTabBar(props: TabBarProps) {
  const { state, descriptors, insets } = props;
  const { t } = useI18n();
  const press = useTabPress(props);
  const reduceMotion = useReducedMotion();
  const [width, setWidth] = useState(0);

  const items: Item[] = [
    { name: "index", label: t("tab_home"), on: "home", off: "home-outline" },
    { name: "requests", label: t("tab_requests"), on: "document-text", off: "document-text-outline" },
    { name: "messages", label: t("tab_messages"), on: "chatbubbles", off: "chatbubbles-outline" },
    { name: "profile", label: t("tab_profile"), on: "stats-chart", off: "stats-chart-outline" },
  ];
  const activeName = state.routes[state.index]?.name;
  const activeIdx = items.findIndex((i) => i.name === activeName);
  const tabW = width / items.length;

  const x = useSharedValue(0);
  const shown = useSharedValue(0);
  const first = React.useRef(true);
  useEffect(() => {
    if (!width) return;
    if (activeIdx < 0) {
      shown.value = withTiming(0, { duration: 180 });
      return;
    }
    const target = activeIdx * tabW;
    shown.value = withTiming(1, { duration: 200 });
    if (first.current || reduceMotion) {
      x.value = target;
      first.current = false;
      return;
    }
    x.value = withTiming(target, { duration: 480, easing: Easing.bezier(0.65, 0, 0.35, 1) });
  }, [activeIdx, width, tabW, x, shown, reduceMotion]);

  const beamStyle = useAnimatedStyle(() => ({ width: tabW, opacity: shown.value, transform: [{ translateX: x.value }] }));

  return (
    <View
      style={[styles.proBar, { paddingBottom: insets.bottom }]}
      onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}
      accessibilityRole="tablist"
    >
      {width > 0 && (
        <Animated.View pointerEvents="none" style={[styles.beam, beamStyle]}>
          <LinearGradient colors={["rgba(255,210,63,0.28)", "rgba(255,210,63,0)"]} style={styles.cone} />
          <View style={styles.laser} />
        </Animated.View>
      )}
      <View style={styles.proRow}>
        {items.map((it, i) => {
          const route = state.routes.find((r) => r.name === it.name);
          const opts = route ? descriptors[route.key]?.options : undefined;
          const focused = i === activeIdx;
          const badge = opts?.tabBarBadge;
          return (
            <Pressable
              key={it.name}
              testID={opts?.tabBarButtonTestID}
              accessibilityRole="tab"
              accessibilityState={{ selected: focused }}
              accessibilityLabel={it.label}
              onPress={() => press(it.name)}
              style={styles.proTab}
            >
              <View>
                <PopIcon name={focused ? it.on : it.off} focused={focused} color={focused ? pro.accent : pro.muted} />
                {badge != null && badge !== "" ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{String(badge)}</Text>
                  </View>
                ) : null}
              </View>
              <Text
                numberOfLines={1}
                style={[styles.proLabel, focused && styles.proLabelOn]}
              >
                {it.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const BAR_H = 68;
const SCAN = 66;

const styles = StyleSheet.create({
  clientWrap: { paddingHorizontal: 16, paddingTop: 14 },
  clientBar: {
    height: BAR_H,
    borderRadius: 999,
    overflow: "visible",
    shadowColor: "#0B5C55",
    shadowOpacity: 0.3,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 10,
  },
  pill: { position: "absolute", top: 10, height: BAR_H - 20, borderRadius: 999 },
  clientSlot: { position: "absolute", top: 0, height: BAR_H, alignItems: "center", justifyContent: "center" },
  scanSlot: {
    position: "absolute",
    left: "50%",
    top: -SCAN / 2 + 4,
    width: SCAN,
    height: SCAN,
    marginLeft: -SCAN / 2,
    alignItems: "center",
    justifyContent: "center",
  },
  scanHalo: { position: "absolute", width: SCAN, height: SCAN, borderRadius: SCAN / 2 },
  scanRing: {
    position: "absolute",
    width: SCAN + 14,
    height: SCAN + 14,
    borderRadius: (SCAN + 14) / 2,
    borderWidth: 2,
    borderStyle: "dashed",
  },
  scanBtn: {
    width: SCAN,
    height: SCAN,
    borderRadius: SCAN / 2,
    borderWidth: 5,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },

  proBar: { backgroundColor: "#0A111C", borderTopWidth: 1, borderTopColor: pro.line },
  proRow: { flexDirection: "row", height: 72 },
  beam: { position: "absolute", top: 0, left: 0, height: 66, alignItems: "center" },
  cone: { position: "absolute", top: 0, left: "18%", right: "18%", bottom: 0, borderBottomLeftRadius: 40, borderBottomRightRadius: 40 },
  laser: {
    width: 44,
    height: 3,
    marginTop: -1,
    borderRadius: 2,
    backgroundColor: pro.accent,
    shadowColor: pro.accent,
    shadowOpacity: 0.9,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
    elevation: 6,
  },
  proTab: { flex: 1, alignItems: "center", justifyContent: "center", gap: 5 },
  proLabel: { fontFamily: fonts.mono, fontSize: 10, letterSpacing: 0.6, textTransform: "uppercase", color: pro.dim },
  proLabelOn: { color: pro.text },
  badge: {
    position: "absolute",
    top: -4,
    right: -10,
    minWidth: 16,
    height: 16,
    paddingHorizontal: 3,
    borderRadius: 8,
    backgroundColor: pro.ok,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeText: { color: pro.bg, fontSize: 10, fontWeight: "800" },
});
