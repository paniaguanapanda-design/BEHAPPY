// "Install the app" card for the web version. Android/desktop Chrome and Edge show the browser's own install
// dialog; on iPhone/iPad (Safari has no install dialog) it explains the two taps needed.
// Hidden once the app runs installed, and on native builds.
import React, { useEffect, useState } from "react";
import { Platform, Pressable, Text, View } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useI18n } from "@/src/i18n";
import { fonts, makeStyles, useTheme } from "@/src/theme";

type BIPEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

let deferred: BIPEvent | null = null;
const listeners = new Set<() => void>();
if (Platform.OS === "web" && typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e as BIPEvent;
    listeners.forEach((l) => l());
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    listeners.forEach((l) => l());
  });
}

const COPY = {
  es: {
    title: "Instala BeHappy",
    sub: "Tenla en tu pantalla de inicio, como una app.",
    button: "Instalar",
    iosTitle: "Instala BeHappy en tu iPhone",
    ios: "Pulsa Compartir y después «Añadir a pantalla de inicio».",
    other: "Abre el menú del navegador (⋮) y elige «Instalar app» o «Añadir a pantalla de inicio».",
    close: "Cerrar",
  },
  it: {
    title: "Installa BeHappy",
    sub: "Tienila nella schermata Home, come un'app.",
    button: "Installa",
    iosTitle: "Installa BeHappy sul tuo iPhone",
    ios: "Tocca Condividi e poi «Aggiungi alla schermata Home».",
    other: "Apri il menu del browser (⋮) e scegli «Installa app» o «Aggiungi a schermata Home».",
    close: "Chiudi",
  },
};

function isStandalone() {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(display-mode: standalone)").matches || (navigator as any).standalone === true;
}
const isIOS = () => typeof navigator !== "undefined" && /iphone|ipad|ipod/i.test(navigator.userAgent);

export function InstallPrompt({ dark = false }: { dark?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { lang } = useI18n();
  const c = COPY[lang === "it" ? "it" : "es"];
  const [, force] = useState(0);
  const [closed, setClosed] = useState(false);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    const l = () => force((n) => n + 1);
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);

  if (Platform.OS !== "web" || closed || isStandalone()) return null;

  const ios = isIOS();
  const install = async () => {
    if (deferred) {
      const ev = deferred;
      deferred = null;
      await ev.prompt();
      await ev.userChoice.catch(() => null);
      force((n) => n + 1);
    } else {
      setHelp(true);
    }
  };

  return (
    <View style={[styles.card, dark && styles.cardDark]} testID="install-prompt">
      <View style={styles.row}>
        <View style={styles.logoWrap}>
          <Image source={require("@/assets/images/logo-house-sun.png")} style={styles.logo} contentFit="contain" />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[styles.title, dark && styles.titleDark]}>{ios ? c.iosTitle : c.title}</Text>
          <Text style={[styles.sub, dark && styles.subDark]}>{ios || help ? (ios ? c.ios : c.other) : c.sub}</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel={c.close} hitSlop={10} onPress={() => setClosed(true)}>
          <Ionicons name="close" size={20} color={dark ? "#FFFFFF" : colors.muted} />
        </Pressable>
      </View>
      {!ios && !help ? (
        <Pressable
          testID="install-button"
          accessibilityRole="button"
          onPress={install}
          style={({ pressed }) => [styles.btn, pressed && { transform: [{ scale: 0.97 }] }]}
        >
          <Ionicons name="download-outline" size={18} color={colors.onSun} />
          <Text style={styles.btnText}>{c.button}</Text>
        </Pressable>
      ) : ios ? (
        <View style={styles.iosRow}>
          <Ionicons name="share-outline" size={22} color={dark ? "#FFFFFF" : colors.brandPrimary} />
          <Ionicons name="arrow-forward" size={16} color={dark ? "#FFFFFF" : colors.muted} />
          <Ionicons name="add-circle-outline" size={22} color={dark ? "#FFFFFF" : colors.brandPrimary} />
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 24, padding: 14, gap: 12, borderWidth: 1, borderColor: c.border },
  cardDark: { backgroundColor: "rgba(255,255,255,0.12)", borderColor: "rgba(255,255,255,0.2)" },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  logoWrap: { width: 48, height: 48, borderRadius: 14, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  logo: { width: 36, height: 36 },
  title: { fontFamily: fonts.displayMedium, fontSize: 17, color: c.onSurface },
  titleDark: { color: "#FFFFFF" },
  sub: { fontSize: 13, color: c.muted, marginTop: 2, lineHeight: 18 },
  subDark: { color: "#E3F3EE" },
  btn: {
    minHeight: 46,
    borderRadius: 999,
    backgroundColor: c.sun,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  btnText: { color: c.onSun, fontWeight: "800", fontSize: 15 },
  iosRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10 },
}));
