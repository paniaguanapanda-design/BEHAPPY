import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, PressableProps, StyleProp, Text, View, ViewStyle } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withSequence, withSpring } from "react-native-reanimated";
import { imageSource } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";

export function Avatar({ uri, name, size = 48 }: { uri?: string | null; name?: string; size?: number }) {
  const styles = useStyles();
  const src = imageSource(uri);
  if (src) return <Image source={src} style={{ width: size, height: size, borderRadius: size / 2 }} contentFit="cover" />;
  return (
    <View style={[styles.avatarFallback, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[styles.avatarText, { fontSize: size * 0.4 }]}>{(name || "?").charAt(0).toUpperCase()}</Text>
    </View>
  );
}

export function BouncyIcon({
  name,
  size,
  color,
  active = false,
}: {
  name: React.ComponentProps<typeof Ionicons>["name"];
  size: number;
  color: React.ComponentProps<typeof Ionicons>["color"];
  active?: boolean;
}) {
  const scale = useSharedValue(1);
  const lift = useSharedValue(0);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (reduceMotion) return;
    if (active) {
      scale.value = withSequence(
        withSpring(1.2, { damping: 7, stiffness: 360 }),
        withSpring(1, { damping: 9, stiffness: 280 }),
      );
      lift.value = withSequence(
        withSpring(-2, { damping: 8, stiffness: 320 }),
        withSpring(0, { damping: 9, stiffness: 280 }),
      );
    } else {
      scale.value = withSpring(1, { damping: 10, stiffness: 300 });
      lift.value = withSpring(0, { damping: 10, stiffness: 300 });
    }
  }, [active, lift, reduceMotion, scale]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }, { translateY: lift.value }],
  }));

  return (
    <Animated.View style={animatedStyle}>
      <Ionicons name={name} size={size} color={color} />
    </Animated.View>
  );
}

type BtnProps = PressableProps & {
  title: string;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  icon?: React.ComponentProps<typeof Ionicons>["name"];
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({ title, variant = "primary", icon, loading, style, disabled, ...rest }: BtnProps) {
  const styles = useStyles();
  const { colors } = useTheme();
  const [pressed, setPressed] = useState(false);
  const bg = { primary: colors.brandPrimary, secondary: colors.brandSecondary, ghost: "transparent", danger: colors.error }[variant];
  const fg = { primary: colors.onBrandPrimary, secondary: colors.onBrandSecondary, ghost: colors.brandPrimary, danger: colors.onError }[variant];
  return (
    <Pressable
      {...rest}
      onPressIn={(event) => {
        setPressed(true);
        rest.onPressIn?.(event);
      }}
      onPressOut={(event) => {
        setPressed(false);
        rest.onPressOut?.(event);
      }}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1, transform: [{ scale: pressed ? 0.98 : 1 }] },
        variant === "ghost" && styles.btnGhost,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon && <BouncyIcon name={icon} size={18} color={fg} active={pressed} />}
          <Text style={[styles.btnText, { color: fg }]} numberOfLines={1}>
            {title}
          </Text>
        </>
      )}
    </Pressable>
  );
}

export function VerifiedBadge({ label, small }: { label?: string; small?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.verified} testID="verified-badge">
      <Ionicons name="shield-checkmark" size={small ? 12 : 14} color={colors.onBrandSecondary} />
      {label ? <Text style={styles.verifiedText}>{label}</Text> : null}
    </View>
  );
}

export function Stars({ value, size = 14 }: { value: number; size?: number }) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: "row", gap: 2 }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Ionicons
          key={i}
          name={value >= i ? "star" : value >= i - 0.5 ? "star-half" : "star-outline"}
          size={size}
          color={colors.warning}
        />
      ))}
    </View>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  const styles = useStyles();
  return <Text style={styles.section}>{children}</Text>;
}

export function Loading() {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface }}>
      <ActivityIndicator color={colors.brandPrimary} size="large" />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  avatarFallback: { backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  avatarText: { color: c.onBrandSecondary, fontWeight: "700" },
  btn: {
    minHeight: 50,
    borderRadius: 12,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  btnGhost: { borderWidth: 1, borderColor: c.border },
  btnText: { fontSize: 16, fontWeight: "600" },
  verified: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: c.brandSecondary,
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  verifiedText: { color: c.onBrandSecondary, fontSize: 12, fontWeight: "700" },
  section: { fontSize: 20, fontWeight: "700", color: c.onSurface, letterSpacing: -0.3 },
}));
