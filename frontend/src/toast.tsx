import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import { Text, View } from "react-native";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { makeStyles, useTheme } from "@/src/theme";

type ToastType = "success" | "error" | "info";
const ToastContext = createContext<(msg: string, type?: ToastType) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; type: ToastType; id: number } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();

  const show = useCallback((msg: string, type: ToastType = "success") => {
    if (timer.current) clearTimeout(timer.current);
    setToast({ msg, type, id: Date.now() });
    timer.current = setTimeout(() => setToast(null), 2800);
  }, []);

  const bg = toast?.type === "error" ? colors.error : toast?.type === "info" ? colors.surfaceInverse : colors.brandPrimary;

  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <Animated.View
          key={toast.id}
          entering={FadeInUp}
          exiting={FadeOutUp}
          pointerEvents="none"
          style={[styles.wrap, { top: insets.top + 8 }]}
        >
          <View testID="toast-message" style={[styles.toast, { backgroundColor: bg }]}>
            <Ionicons
              name={toast.type === "error" ? "alert-circle" : "checkmark-circle"}
              size={20}
              color={colors.onBrandPrimary}
            />
            <Text style={styles.text}>{toast.msg}</Text>
          </View>
        </Animated.View>
      )}
    </ToastContext.Provider>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: { position: "absolute", left: 16, right: 16, zIndex: 1000, elevation: 1000 },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    shadowColor: c.surfaceInverse,
    shadowOpacity: 0.2,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  text: { color: c.onBrandPrimary, fontSize: 14, fontWeight: "600", flex: 1 },
}));

export const useToast = () => useContext(ToastContext);
