// Web only: Google's official sign-in button right on the login screen (one tap, no extra sheet).
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, View } from "react-native";
import { useI18n } from "@/src/i18n";
import { useTheme } from "@/src/theme";

const CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;

export function GoogleWebButton({ onToken, onError }: { onToken: (idToken: string) => void; onError: (e: Error) => void }) {
  const ref = useRef<View>(null);
  const { lang } = useI18n();
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const [ready, setReady] = useState(false);
  const cb = useRef({ onToken, onError });
  useEffect(() => {
    cb.current = { onToken, onError };
  }, [onToken, onError]);

  useEffect(() => {
    const el = ref.current as unknown as HTMLElement | null;
    if (!el || !width || !CLIENT_ID) return;
    import("@/src/googleWeb")
      .then(({ renderGoogleButton }) => renderGoogleButton(el, CLIENT_ID, lang, width, (t) => cb.current.onToken(t)))
      .then(() => setReady(true))
      .catch((e) => cb.current.onError(e));
  }, [width, lang]);

  return (
    <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)} style={{ minHeight: 44, alignItems: "center", justifyContent: "center" }}>
      <View ref={ref} testID="google-login-button" />
      {!ready ? <ActivityIndicator color={colors.muted} style={{ position: "absolute" }} /> : null}
    </View>
  );
}
