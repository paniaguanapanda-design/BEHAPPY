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
import { I18nProvider } from "@/src/i18n";
import { ToastProvider } from "@/src/toast";
import { AppSplash } from "@/src/AppSplash";
import { CameraPermissionPrompt } from "@/src/CameraPermissionPrompt";
import { initializeRevenueCat, SubscriptionProvider } from "@/src/revenuecat";

LogBox.ignoreAllLogs(true);

try {
  initializeRevenueCat();
} catch (err) {
  console.warn("RevenueCat unavailable:", err);
}

function Gate() {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const [splashDone, setSplashDone] = useState(false);

  useEffect(() => {
    const h = setTimeout(() => setSplashDone(true), 1600);
    return () => clearTimeout(h);
  }, []);

  useEffect(() => {
    if (loading) return;
    const onLogin = segments[0] === "login";
    if (!user && !onLogin) router.replace("/login");
    else if (user && onLogin) router.replace("/");
  }, [user, loading, segments, router]);

  if (loading || !splashDone) return <AppSplash />;
  return (
    <SubscriptionProvider userId={user?.user_id ?? null}>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="scan" options={{ animation: "slide_from_bottom" }} />
      </Stack>
      {user && <CameraPermissionPrompt />}
    </SubscriptionProvider>
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
