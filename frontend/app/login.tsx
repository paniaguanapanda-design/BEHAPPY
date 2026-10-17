import React, { useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { Button } from "@/src/ui";
import { makeStyles, useTheme } from "@/src/theme";
import { LangToggle } from "@/src/LangToggle";

const HERO = "https://images.unsplash.com/photo-1686890363933-4a1125d4e3b0?w=1000&q=80";

export default function Login() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { t } = useI18n();
  const { login, register, loginWithGoogle } = useAuth();
  const toast = useToast();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [gBusy, setGBusy] = useState(false);

  const submit = async () => {
    if (!email || !password || (mode === "up" && !name)) return toast(t("required"), "error");
    setBusy(true);
    try {
      if (mode === "in") await login(email, password);
      else await register(name, email, password);
    } catch (e: any) {
      toast(e.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  const google = async () => {
    setGBusy(true);
    try {
      await loginWithGoogle();
    } catch (e: any) {
      toast(e.message || t("error_generic"), "error");
    } finally {
      setGBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ paddingBottom: insets.bottom + 24 }} keyboardShouldPersistTaps="handled">
        <View style={styles.hero}>
          <Image source={{ uri: HERO }} style={StyleSheetAbs} contentFit="cover" />
          <LinearGradient colors={["transparent", colors.surfaceInverse]} style={StyleSheetAbs} />
          <View style={[styles.heroTop, { paddingTop: insets.top + 12 }]}>
            <View style={styles.logo}>
              <Ionicons name="construct" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.logoText}>FixAI</Text>
            </View>
            <LangToggle dark />
          </View>
          <View style={styles.heroBottom}>
            <Text style={styles.title}>{t("login_title")}</Text>
            <Text style={styles.sub}>{t("login_sub")}</Text>
          </View>
        </View>

        <View style={styles.form}>
          {mode === "up" && (
            <TextInput testID="register-name-input" style={styles.input} placeholder={t("name")} placeholderTextColor={colors.muted} value={name} onChangeText={setName} />
          )}
          <TextInput
            testID="login-email-input"
            style={styles.input}
            placeholder={t("email")}
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
          />
          <TextInput
            testID="login-password-input"
            style={styles.input}
            placeholder={t("password")}
            placeholderTextColor={colors.muted}
            secureTextEntry
            value={password}
            onChangeText={setPassword}
            onSubmitEditing={submit}
          />
          <Button testID="login-submit-button" title={mode === "in" ? t("sign_in") : t("sign_up")} onPress={submit} loading={busy} />
          <View style={styles.orRow}>
            <View style={styles.line} />
            <Text style={styles.or}>{t("or")}</Text>
            <View style={styles.line} />
          </View>
          <Button testID="google-login-button" variant="ghost" icon="logo-google" title={t("continue_google")} onPress={google} loading={gBusy} />
          <Pressable testID="toggle-auth-mode" onPress={() => setMode(mode === "in" ? "up" : "in")} style={styles.switch}>
            <Text style={styles.switchText}>{mode === "in" ? t("no_account") : t("have_account")}</Text>
          </Pressable>
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}

const StyleSheetAbs = { position: "absolute" as const, top: 0, left: 0, right: 0, bottom: 0 };

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  hero: { height: 380, justifyContent: "space-between", overflow: "hidden" },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 24 },
  logo: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.brandPrimary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999 },
  logoText: { color: c.onBrandPrimary, fontWeight: "800", fontSize: 16 },
  heroBottom: { padding: 24, gap: 8 },
  title: { color: c.onSurfaceInverse, fontSize: 32, fontWeight: "800", letterSpacing: -0.8, lineHeight: 36 },
  sub: { color: c.onSurfaceInverse, opacity: 0.85, fontSize: 15, lineHeight: 21 },
  form: { padding: 24, gap: 12 },
  input: {
    height: 52,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    paddingHorizontal: 16,
    fontSize: 16,
    color: c.onSurface,
  },
  orRow: { flexDirection: "row", alignItems: "center", gap: 12, marginVertical: 4 },
  line: { flex: 1, height: 1, backgroundColor: c.divider },
  or: { color: c.muted, fontSize: 13 },
  switch: { alignItems: "center", paddingVertical: 12, minHeight: 44 },
  switchText: { color: c.brandTertiary, fontWeight: "600", fontSize: 14 },
}));
