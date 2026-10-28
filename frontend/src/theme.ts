// Design tokens for this app (light theme). Keys match the "color" block of /app/design_guidelines.json.
import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  // Same palette as be-happyapp.com: orange + navy on cool light greys.
  surface: "#F4F6F9",
  onSurface: "#0A1628",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#0A1628",
  surfaceTertiary: "#EAEEF3",
  onSurfaceTertiary: "#46546A",
  surfaceInverse: "#0A1628",
  onSurfaceInverse: "#FFFFFF",
  muted: "#5F6B7E",

  // Orange buttons carry navy text (6.5:1); white on orange is only 2.9:1.
  brand: "#FF6B00",
  onBrand: "#0A1628",
  brandPrimary: "#FF6B00",
  onBrandPrimary: "#0A1628",
  brandSecondary: "#FFF4EB",
  onBrandSecondary: "#9A3F00",
  brandTertiary: "#1E3A5F",
  onBrandTertiary: "#FFFFFF",

  success: "#34C759",
  onSuccess: "#FFFFFF",
  warning: "#FF9500",
  onWarning: "#FFFFFF",
  error: "#FF3B30",
  onError: "#FFFFFF",
  info: "#007AFF",
  onInfo: "#FFFFFF",

  border: "#E1E6ED",
  borderStrong: "#C7CFDA",
  divider: "#E1E6ED",
  scrim: "rgba(10,22,40,0.55)",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;

export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
// Display face for titles, embedded at build time by the expo-font plugin (app.json).
export const fonts = { display: "BricolageGrotesque_800ExtraBold" };

export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = (system === "light" || system === "dark") && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
