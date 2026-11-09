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

// The install announcement is caught by a tiny script in public/index.html (it often fires before this bundle
// loads) and kept on window.__bip; "bip-change" tells us when it arrives or the app gets installed.
const w = (typeof window !== "undefined" ? window : {}) as Window & { __bip?: BIPEvent | null; __bipInstalled?: boolean };
const getDeferred = () => (Platform.OS === "web" ? w.__bip ?? null : null);

const COPY = {
  es: {
    title: "Instala BeHappy",
    sub: "Tenla en tu pantalla de inicio, como una app.",
    button: "Instalar",
    iosTitle: "Instala BeHappy en tu iPhone",
    ios: "Pulsa Compartir y después «Añadir a pantalla de inicio».",
    other: "Abre el menú del navegador (⋮) y elige «Instalar app» o «Añadir a pantalla de inicio».",
    close: "Cerrar",
    waiting: "Preparando la instalación…",
    done: "¡Instalada! Búscala en tu pantalla de inicio.",
  },
  it: {
    title: "Installa BeHappy",
    sub: "Tienila nella schermata Home, come un'app.",
    button: "Installa",
    iosTitle: "Installa BeHappy sul tuo iPhone",
    ios: "Tocca Condividi e poi «Aggiungi alla schermata Home».",
    other: "Apri il menu del browser (⋮) e scegli «Installa app» o «Aggiungi a schermata Home».",
    close: "Chiudi",
    waiting: "Preparo l'installazione…",
    done: "Installata! La trovi nella schermata Home.",
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
  const [waiting, setWaiting] = useState(false);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined") return;
    const l = () => {
      if (w.__bipInstalled) setInstalled(true);
      force((n) => n + 1);
    };
    window.addEventListener("bip-change", l);
    return () => window.removeEventListener("bip-change", l);
  }, []);

  if (Platform.OS !== "web" || closed || isStandalone()) return null;

  const ios = isIOS();
  // Opens the browser's own install dialog; one more tap on its "Instalar" and the app is installed.
  const openDialog = async (ev: BIPEvent) => {
    w.__bip = null; // the browser lets each announcement be used once
    await ev.prompt();
    const choice = await ev.userChoice.catch(() => null);
    if (choice?.outcome === "accepted") setInstalled(true);
    force((n) => n + 1);
  };
  const install = async () => {
    const ev = getDeferred();
    if (ev) return openDialog(ev);
    // Chrome may still be checking the app: wait a few seconds for it before falling back to the steps.
    setWaiting(true);
    const ready = await new Promise<BIPEvent | null>((resolve) => {
      const t = setTimeout(() => {
        window.removeEventListener("bip-change", on);
        resolve(getDeferred());
      }, 4000);
      const on = () => {
        if (getDeferred()) {
          clearTimeout(t);
          window.removeEventListener("bip-change", on);
          resolve(getDeferred());
        }
      };
      window.addEventListener("bip-change", on);
    });
    setWaiting(false);
    if (ready) return openDialog(ready);
    setHelp(true);
  };

  if (installed) {
    return (
      <View style={[styles.card, dark && styles.cardDark]} testID="install-done">
        <View style={styles.row}>
          <Ionicons name="checkmark-circle" size={28} color={colors.success} />
          <Text style={[styles.title, { flex: 1 }, dark && styles.titleDark]}>{c.done}</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.card, dark && styles.cardDark]} testID="install-prompt">
      <View style={styles.row}>
        <View style={styles.logoWrap}>
          <Image source={require("@/assets/images/logo-house-sun.png")} style={styles.logo} contentFit="contain" />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[styles.title, dark && styles.titleDark]}>{ios ? c.iosTitle : c.title}</Text>
          <Text style={[styles.sub, dark && styles.subDark]}>{waiting ? c.waiting : ios || help ? (ios ? c.ios : c.other) : c.sub}</Text>
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
          disabled={waiting}
          style={({ pressed }) => [styles.btn, (pressed || waiting) && { transform: [{ scale: 0.97 }], opacity: waiting ? 0.7 : 1 }]}
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
