// Design tokens for this app (light theme). Keys match the "color" block of /app/design_guidelines.json.
import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FAF9F6",
  onSurface: "#1C1B19",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#1C1B19",
  surfaceTertiary: "#F0EDE6",
  onSurfaceTertiary: "#4A4844",
  surfaceInverse: "#1C1B19",
  onSurfaceInverse: "#FFFFFF",
  muted: "#8B8881",

  brand: "#2D4A22",
  onBrand: "#FFFFFF",
  brandPrimary: "#2D4A22",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E8F0E4",
  onBrandSecondary: "#2D4A22",
  brandTertiary: "#4A7A3A",
  onBrandTertiary: "#FFFFFF",

  success: "#34C759",
  onSuccess: "#FFFFFF",
  warning: "#FF9500",
  onWarning: "#FFFFFF",
  error: "#FF3B30",
  onError: "#FFFFFF",
  info: "#007AFF",
  onInfo: "#FFFFFF",

  border: "#E5E3DF",
  borderStrong: "#CFCBC5",
  divider: "#E5E3DF",
  scrim: "rgba(28,27,25,0.55)",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;

export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
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
