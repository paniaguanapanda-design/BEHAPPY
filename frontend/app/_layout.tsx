import { useEffect, useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { LogBox, StyleSheet } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider, useAuth } from "@/src/auth";
import { I18nProvider, useI18n } from "@/src/i18n";
import { ToastProvider } from "@/src/toast";
import { AppSplash } from "@/src/AppSplash";
import { CameraPermissionPrompt } from "@/src/CameraPermissionPrompt";
import { takeAfterLogin } from "@/src/postLogin";
import { usePushSetup } from "@/src/push";

LogBox.ignoreAllLogs(true);

function Gate() {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const [splashDone, setSplashDone] = useState(false);
  const { lang } = useI18n();
  usePushSetup(user?.user_id ?? null, lang);

  useEffect(() => {
    const h = setTimeout(() => setSplashDone(true), 1600);
    return () => clearTimeout(h);
  }, []);

  useEffect(() => {
    if (loading) return;
    const onLogin = segments[0] === "login";
    const isPublic = onLogin || segments[0] === "pro"; // the specialists page is readable before signing in
    if (!user && !isPublic) router.replace("/login");
    else if (user && isPublic) {
      const next = takeAfterLogin();
      router.replace("/");
      if (next) router.push(next as any); // e.g. a new specialist goes straight to their profile form
    }
  }, [user, loading, segments, router]);

  if (loading || !splashDone) return <AppSplash />;
  return (
    <>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="scan" options={{ animation: "slide_from_bottom" }} />
      </Stack>
      {user && <CameraPermissionPrompt />}
    </>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <KeyboardProvider>
            <I18nProvider>
              <ToastProvider>
                <AuthProvider>
                  <StatusBar style="dark" />
                  <Gate />
                </AuthProvider>
              </ToastProvider>
            </I18nProvider>
          </KeyboardProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
