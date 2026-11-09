import React, { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useFocusEffect, useRouter } from "expo-router";
import { useAuth } from "@/src/auth";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { Button } from "@/src/ui";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { LangToggle } from "@/src/LangToggle";
import { InstallPrompt } from "@/src/InstallPrompt";
import { setAfterLogin, takeProIntent } from "@/src/postLogin";

const LOGO = require("@/assets/images/logo-house-sun.png");
// The same photo as the website: a phone scanning a dripping faucet.
const HERO = require("@/assets/images/login-hero.jpg");
const GOOGLE_G = require("@/assets/images/google-g.png");

export default function Login() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { t, lang } = useI18n();
  const { login, register, loginWithGoogle, resetPassword } = useAuth();
  const toast = useToast();
  const [mode, setMode] = useState<"in" | "up" | "forgot" | "reset">("in");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [gBusy, setGBusy] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [pro, setPro] = useState(false); // came from the specialists page: after signing up, open the profile form
  const router = useRouter();

  useFocusEffect(
    useCallback(() => {
      const intent = takeProIntent();
      if (intent) {
        setPro(true);
        setMode(intent);
      }
    }, []),
  );
  // Read by the auth gate right after signing in.
  setAfterLogin(pro ? "/specialist-form" : null);

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

  const sendCode = async () => {
    if (!email.trim()) return toast(t("required"), "error");
    setBusy(true);
    try {
      await api("/auth/forgot-password", { body: { email: email.trim(), language: lang } });
      setMode("reset");
      toast(t("code_sent"));
    } catch (e: any) {
      toast(e.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async () => {
    if (code.trim().length !== 6 || newPassword.length < 6) return toast(t("required"), "error");
    setBusy(true);
    try {
      await resetPassword(email.trim(), code.trim(), newPassword);
      toast(t("password_changed"));
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
          <Image source={HERO} style={StyleSheetAbs} contentFit="cover" contentPosition={{ left: "62%", top: "40%" }} />
          <LinearGradient
            colors={["rgba(10,22,40,0.6)", "rgba(10,22,40,0.2)", colors.surfaceInverse]}
            locations={[0, 0.4, 1]}
            style={StyleSheetAbs}
          />
          <View style={[styles.heroTop, { paddingTop: insets.top + 8 }]}>
            <View style={styles.logo} testID="app-logo" accessible accessibilityLabel="BeHappy">
              <Image source={LOGO} style={styles.logoImg} contentFit="contain" />
              <Text style={styles.logoText}>BeHappy</Text>
            </View>
            <LangToggle dark />
          </View>
          <View style={styles.heroBottom}>
            <Text style={styles.title}>{pro ? t(mode === "up" ? "pro_signup_title" : "pro_signin_title") : t("login_title")}</Text>
            <Text style={styles.sub}>{pro ? t(mode === "up" ? "pro_signup_sub" : "pro_signin_sub") : t("login_sub")}</Text>
          </View>
        </View>

        {mode === "forgot" || mode === "reset" ? (
          <View style={styles.form} testID="forgot-password-form">
            <Text style={styles.formTitle}>{t("forgot_title")}</Text>
            <Text style={styles.formText}>{mode === "forgot" ? t("forgot_text") : t("code_sent")}</Text>
            <TextInput
              testID="forgot-email-input"
              style={styles.input}
              placeholder={t("email")}
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
              editable={mode === "forgot"}
              value={email}
              onChangeText={setEmail}
            />
            {mode === "forgot" ? (
              <Button testID="send-code-button" title={t("send_code")} onPress={sendCode} loading={busy} />
            ) : (
              <>
                <TextInput
                  testID="reset-code-input"
                  style={[styles.input, styles.codeInput]}
                  placeholder={t("code")}
                  placeholderTextColor={colors.muted}
                  keyboardType="number-pad"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={code}
                  onChangeText={(v) => setCode(v.replace(/\D/g, ""))}
                />
                <TextInput
                  testID="reset-new-password-input"
                  style={styles.input}
                  placeholder={t("new_password")}
                  placeholderTextColor={colors.muted}
                  secureTextEntry
                  autoComplete="new-password"
                  value={newPassword}
                  onChangeText={setNewPassword}
                  onSubmitEditing={changePassword}
                />
                <Button testID="change-password-button" title={t("change_password")} onPress={changePassword} loading={busy} />
                <Pressable testID="resend-code-button" onPress={sendCode} disabled={busy} style={styles.switch}>
                  <Text style={styles.switchText}>{t("resend_code")}</Text>
                </Pressable>
              </>
            )}
            <Pressable testID="back-to-login" onPress={() => setMode("in")} style={styles.switch}>
              <Text style={styles.switchText}>{t("back_to_login")}</Text>
            </Pressable>
          </View>
        ) : (
        <View style={styles.form}>
          <InstallPrompt />
          <Pressable
            testID="google-login-button"
            onPress={google}
            disabled={gBusy}
            style={({ pressed }) => [styles.google, { transform: [{ scale: pressed ? 0.97 : 1 }] }]}
          >
            {gBusy ? (
              <ActivityIndicator color={colors.onSurface} />
            ) : (
              <>
                <Image source={GOOGLE_G} style={styles.gIcon} contentFit="contain" />
                <Text style={styles.googleText}>{t("continue_google")}</Text>
              </>
            )}
          </Pressable>
          <View style={styles.orRow}>
            <View style={styles.line} />
            <Text style={styles.or}>{t("or_email")}</Text>
            <View style={styles.line} />
          </View>
          {mode === "up" && (
            <TextInput testID="register-name-input" style={styles.input} placeholder={t("name")} placeholderTextColor={colors.muted} autoComplete="name" value={name} onChangeText={setName} />
          )}
          <TextInput
            testID="login-email-input"
            style={styles.input}
            placeholder={t("email")}
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
            value={email}
            onChangeText={setEmail}
          />
          <View>
            <TextInput
              testID="login-password-input"
              style={[styles.input, styles.pwInput]}
              placeholder={t("password")}
              placeholderTextColor={colors.muted}
              secureTextEntry={!showPw}
              autoCapitalize="none"
              autoComplete={mode === "up" ? "new-password" : "current-password"}
              value={password}
              onChangeText={setPassword}
              onSubmitEditing={submit}
            />
            <Pressable
              testID="toggle-password-visibility"
              onPress={() => setShowPw((v) => !v)}
              style={styles.eye}
              hitSlop={8}
              accessibilityRole="button"
              accessibilityLabel={t(showPw ? "hide_password" : "show_password")}
            >
              <Ionicons name={showPw ? "eye-off-outline" : "eye-outline"} size={22} color={colors.muted} />
            </Pressable>
          </View>
          {mode === "in" && (
            <Pressable testID="forgot-password-link" onPress={() => setMode("forgot")} style={styles.forgot} hitSlop={8}>
              <Text style={styles.forgotText}>{t("forgot_password")}</Text>
            </Pressable>
          )}
          <Button testID="login-submit-button" title={mode === "in" ? t("sign_in") : t("sign_up")} onPress={submit} loading={busy} />
          <Pressable testID="toggle-auth-mode" onPress={() => setMode(mode === "in" ? "up" : "in")} style={styles.switch}>
            <Text style={styles.switchText}>{mode === "in" ? t("no_account") : t("have_account")}</Text>
          </Pressable>

          {!pro && (
            <Pressable
              testID="pro-card"
              onPress={() => router.push("/pro")}
              style={({ pressed }) => [styles.pro, { transform: [{ scale: pressed ? 0.98 : 1 }] }]}
            >
              <View style={styles.proIcon}>
                <Ionicons name="briefcase-outline" size={20} color={colors.onBrandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.proTitle}>{t("pro_card_title")}</Text>
                <Text style={styles.proText}>{t("pro_card_text")}</Text>
              </View>
              <Ionicons name="arrow-forward" size={20} color={colors.brandPrimary} />
            </Pressable>
          )}

          <View style={styles.legalRow}>
            <Text style={styles.legalText} onPress={() => Linking.openURL("https://www.be-happyapp.com/privacy")}>
              {lang === "it" ? "Privacy" : "Privacidad"}
            </Text>
            <Text style={styles.legalText}> · </Text>
            <Text style={styles.legalText} onPress={() => Linking.openURL("https://www.be-happyapp.com/termini")}>
              {lang === "it" ? "Termini" : "Términos"}
            </Text>
          </View>
        </View>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

const StyleSheetAbs = { position: "absolute" as const, top: 0, left: 0, right: 0, bottom: 0 };

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  hero: { height: 340, justifyContent: "space-between", overflow: "hidden", backgroundColor: c.surfaceInverse },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 16 },
  logo: { flexDirection: "row", alignItems: "center", gap: 8 },
  logoImg: { width: 34, height: 34 },
  logoText: { color: c.onSurfaceInverse, fontSize: 22, fontFamily: fonts.display, letterSpacing: -0.3 },
  heroBottom: { paddingHorizontal: 22, paddingBottom: 22, gap: 8 },
  title: { color: c.onSurfaceInverse, fontSize: 34, fontFamily: fonts.display, letterSpacing: -0.8, lineHeight: 36 },
  sub: { color: c.onSurfaceInverse, opacity: 0.82, fontSize: 15, lineHeight: 21 },
  form: { paddingHorizontal: 20, paddingTop: 20, gap: 12 },
  google: {
    height: 54,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  gIcon: { width: 20, height: 20 },
  googleText: { color: c.onSurface, fontSize: 16, fontWeight: "600" },
  input: {
    height: 52,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.surfaceSecondary,
    paddingHorizontal: 16,
    fontSize: 16,
    color: c.onSurface,
  },
  pwInput: { paddingRight: 52 },
  eye: { position: "absolute", right: 6, top: 4, width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  orRow: { flexDirection: "row", alignItems: "center", gap: 12, marginVertical: 2 },
  line: { flex: 1, height: 1, backgroundColor: c.divider },
  or: { color: c.muted, fontSize: 13 },
  pro: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: c.surfaceSecondary,
    borderWidth: 1,
    borderColor: c.border,
    borderRadius: 18,
    padding: 14,
    marginTop: 4,
  },
  proIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  proTitle: { fontSize: 16, fontFamily: fonts.display, color: c.onSurface },
  proText: { fontSize: 13, color: c.muted, marginTop: 2 },
  legalRow: { flexDirection: "row", justifyContent: "center", marginTop: 4 },
  legalText: { color: c.muted, fontSize: 13, textDecorationLine: "underline" },
  switch: { alignItems: "center", paddingVertical: 12, minHeight: 44 },
  forgot: { alignSelf: "flex-end", minHeight: 32, justifyContent: "center" },
  forgotText: { color: c.brandTertiary, fontWeight: "600", fontSize: 13 },
  formTitle: { fontSize: 22, fontFamily: fonts.display, color: c.onSurface },
  formText: { fontSize: 14, lineHeight: 20, color: c.muted },
  codeInput: { fontSize: 22, letterSpacing: 6, textAlign: "center" },
  switchText: { color: c.brandTertiary, fontWeight: "600", fontSize: 14 },
}));
