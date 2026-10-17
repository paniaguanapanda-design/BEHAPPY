import React from "react";
import { ActivityIndicator, Pressable, PressableProps, StyleProp, Text, View, ViewStyle } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { imageUri } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";

export function Avatar({ uri, name, size = 48 }: { uri?: string | null; name?: string; size?: number }) {
  const styles = useStyles();
  const src = imageUri(uri);
  if (src) return <Image source={{ uri: src }} style={{ width: size, height: size, borderRadius: size / 2 }} contentFit="cover" />;
  return (
    <View style={[styles.avatarFallback, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[styles.avatarText, { fontSize: size * 0.4 }]}>{(name || "?").charAt(0).toUpperCase()}</Text>
    </View>
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
  const bg = { primary: colors.brandPrimary, secondary: colors.brandSecondary, ghost: "transparent", danger: colors.error }[variant];
  const fg = { primary: colors.onBrandPrimary, secondary: colors.onBrandSecondary, ghost: colors.brandPrimary, danger: colors.onError }[variant];
  return (
    <Pressable
      {...rest}
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
          {icon && <Ionicons name={icon} size={18} color={fg} />}
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
