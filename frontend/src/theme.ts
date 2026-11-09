// Design tokens for this app (light theme). Keys match the "color" block of /app/design_guidelines.json.
import { useMemo, useSyncExternalStore } from "react";
import { Appearance, Platform, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  // BE HAPPY "fresh & calm": deep teal + sunny yellow on a mint-white ground.
  surface: "#F2FBF7",
  onSurface: "#0E2A27",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#0E2A27",
  surfaceTertiary: "#E3F3EE",
  onSurfaceTertiary: "#35524E",
  surfaceInverse: "#0B5C55",
  onSurfaceInverse: "#FFFFFF",
  muted: "#4A6662",

  // Teal carries white text (7.6:1) and is safe as a text/icon tint on light grounds.
  brand: "#0B5C55",
  onBrand: "#FFFFFF",
  brandPrimary: "#0B5C55",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#D6F0E8",
  onBrandSecondary: "#0B5C55",
  brandTertiary: "#0E2A27",
  onBrandTertiary: "#FFFFFF",

  // Sunny yellow: the "happy" accent for the main call to action (scan) and highlights. Always dark text on it.
  sun: "#FFD23F",
  onSun: "#0E2A27",
  sunSoft: "#FFF4C7",

  success: "#1E8E5A",
  onSuccess: "#FFFFFF",
  warning: "#F2A900",
  onWarning: "#0E2A27",
  error: "#D93A2B",
  onError: "#FFFFFF",
  info: "#1F6FD1",
  onInfo: "#FFFFFF",

  border: "#CFE6DE",
  borderStrong: "#A9D9C9",
  divider: "#E3F3EE",
  scrim: "rgba(14,42,39,0.55)",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;

export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
// Display face for titles (Fredoka) and a monospace for the Pro data (JetBrains Mono), loaded in app/_layout.tsx.
export const fonts = {
  display: "Fredoka_700Bold",
  displayMedium: "Fredoka_600SemiBold",
  mono: "JetBrainsMono_500Medium",
};

export const radius = { sm: 8, md: 16, lg: 24, pill: 999 };

// The specialist area ("Zona Pro") keeps a dark, technical look; the yellow is the shared thread with the client side.
export const pro = {
  bg: "#05090F",
  surface: "#0E1624",
  card: "#172235",
  line: "#263247",
  text: "#E8EDF5",
  muted: "#A9B4C4",
  dim: "#8592A6",
  accent: "#FFD23F",
  onAccent: "#05090F",
  ok: "#4ADE80",
};

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

setColorScheme?.(themes.dark ? null : defaultScheme);

// "Zona Pro": specialists see the whole app in a dark, technical palette (same keys, so every screen follows).
const proColors: ThemeColors = {
  surface: "#0E1624",
  onSurface: "#E8EDF5",
  surfaceSecondary: "#172235",
  onSurfaceSecondary: "#E8EDF5",
  surfaceTertiary: "#1E2B40",
  onSurfaceTertiary: "#A9B4C4",
  surfaceInverse: "#05090F",
  onSurfaceInverse: "#FFFFFF",
  muted: "#A9B4C4",
  brand: "#FFD23F",
  onBrand: "#05090F",
  brandPrimary: "#FFD23F",
  onBrandPrimary: "#05090F",
  brandSecondary: "#263247",
  onBrandSecondary: "#FFD23F",
  brandTertiary: "#E8EDF5",
  onBrandTertiary: "#05090F",
  sun: "#FFD23F",
  onSun: "#05090F",
  sunSoft: "#2B2A1C",
  success: "#4ADE80",
  onSuccess: "#05090F",
  warning: "#FBBF24",
  onWarning: "#05090F",
  error: "#F87171",
  onError: "#05090F",
  info: "#60A5FA",
  onInfo: "#05090F",
  border: "#263247",
  borderStrong: "#34435C",
  divider: "#1E2B40",
  scrim: "rgba(0,0,0,0.6)",
};

let proMode = false;
const proListeners = new Set<() => void>();
export function setProMode(on: boolean) {
  if (proMode === on) return;
  proMode = on;
  proListeners.forEach((l) => l());
  if (Platform.OS === "web" && typeof document !== "undefined") {
    const bg = on ? proColors.surface : light.surface;
    document.body.style.backgroundColor = bg;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
  }
}
const subscribePro = (l: () => void) => {
  proListeners.add(l);
  return () => {
    proListeners.delete(l);
  };
};
const getPro = () => proMode;

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const isPro = useSyncExternalStore(subscribePro, getPro, getPro);
  if (isPro) return { scheme: "dark", colors: proColors };
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
