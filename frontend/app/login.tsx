import React, { useState } from "react";
import { Linking, Pressable, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { useAuth } from "@/src/auth";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { Button } from "@/src/ui";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { LangToggle } from "@/src/LangToggle";

const LOGO = require("@/assets/images/behappy-logo.png");
const HERO = "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=1000&q=80";

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
          <Image source={{ uri: HERO }} style={StyleSheetAbs} contentFit="cover" />
          <LinearGradient colors={["transparent", colors.surfaceInverse]} style={StyleSheetAbs} />
          <View style={[styles.heroTop, { paddingTop: insets.top + 12 }]}>
            <View style={styles.logo} testID="app-logo">
              <Image source={LOGO} style={styles.logoImg} contentFit="contain" />
              <Text style={styles.logoText}>BE HAPPY</Text>
            </View>
          </View>
          <View style={styles.heroBottom}>
            <Text style={styles.title}>{t("login_title")}</Text>
            <Text style={styles.sub}>{t("login_sub")}</Text>
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
          {mode === "in" && (
            <Pressable testID="forgot-password-link" onPress={() => setMode("forgot")} style={styles.forgot} hitSlop={8}>
              <Text style={styles.forgotText}>{t("forgot_password")}</Text>
            </Pressable>
          )}
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
          <View style={styles.legalRow}>
            <Text style={styles.legalText} onPress={() => Linking.openURL("https://www.be-happyapp.com/privacy")}>
              {lang === "it" ? "Privacy" : "Privacidad"}
            </Text>
            <Text style={styles.legalText}> · </Text>
            <Text style={styles.legalText} onPress={() => Linking.openURL("https://www.be-happyapp.com/termini")}>
              {lang === "it" ? "Termini" : "Términos"}
            </Text>
          </View>
          <View style={styles.langBottom}>
            <Ionicons name="language" size={18} color={colors.muted} />
            <LangToggle />
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
  hero: { height: 380, justifyContent: "space-between", overflow: "hidden" },
  heroTop: { flexDirection: "row", justifyContent: "center", alignItems: "center", paddingHorizontal: 24 },
  logo: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: c.surface, paddingLeft: 6, paddingRight: 16, paddingVertical: 6, borderRadius: 999 },
  logoImg: { width: 32, height: 32, borderRadius: 16 },
  logoText: { color: c.onSurface, fontWeight: "800", fontSize: 16, letterSpacing: 0.5 },
  heroBottom: { padding: 24, gap: 8, alignItems: "center" },
  title: { color: c.onSurfaceInverse, fontSize: 32, fontFamily: fonts.display, letterSpacing: -0.8, lineHeight: 36, textAlign: "center" },
  sub: { color: c.onSurfaceInverse, opacity: 0.85, fontSize: 15, lineHeight: 21, textAlign: "center" },
  langBottom: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 8 },
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
