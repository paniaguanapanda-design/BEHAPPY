import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import { api, setToken, setUnauthorizedHandler } from "@/src/api";
import { setProMode } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const TOKEN_KEY = "auth_token";
// Last signed-in user, so the app opens at once even while the server is waking up.
const USER_KEY = "auth_user";
const GOOGLE_WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;

export type User = {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  role: "client" | "specialist";
  specialist_id?: string | null;
};

type Ctx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  resetPassword: (email: string, code: string, newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<Ctx>(null as unknown as Ctx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const remember = useCallback((u: User) => storage.setItem(USER_KEY, JSON.stringify(u)), []);

  const clear = useCallback(async () => {
    await storage.secureRemove(TOKEN_KEY);
    await storage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const applySession = useCallback(async (res: { session_token: string; user: User }) => {
    await storage.secureSet(TOKEN_KEY, res.session_token);
    setToken(res.session_token);
    setUser(res.user);
    remember(res.user);
  }, [remember]);

  useEffect(() => {
    setProMode(user?.role === "specialist" && !!user.specialist_id);
  }, [user]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clear();
    });
    (async () => {
      try {
        const stored = await storage.secureGet(TOKEN_KEY, null);
        if (typeof stored === "string" && stored) {
          setToken(stored);
          let cached: User | null = null;
          try {
            const raw = await storage.getItem(USER_KEY, null);
            cached = typeof raw === "string" ? (JSON.parse(raw) as User) : null;
          } catch {}
          if (cached) {
            // Open now with the remembered user and confirm with the server in the background.
            // A rejected session (401) still signs out through the unauthorized handler.
            setUser(cached);
            setLoading(false);
            api<User>("/auth/me")
              .then((fresh) => {
                setUser(fresh);
                remember(fresh);
              })
              .catch(() => {});
          } else {
            try {
              const fresh = await api<User>("/auth/me");
              setUser(fresh);
              remember(fresh);
            } catch {
              await clear();
            }
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [clear, remember]);

  const login = useCallback(
    async (email: string, password: string) => {
      await applySession(await api("/auth/login", { body: { email, password } }));
    },
    [applySession],
  );

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      await applySession(await api("/auth/register", { body: { name, email, password } }));
    },
    [applySession],
  );

  const loginWithGoogle = useCallback(async () => {
    if (!GOOGLE_WEB_CLIENT_ID) throw new Error("Google no esta configurado.");
    if (Platform.OS === "web") {
      const { googleWebIdToken } = await import("@/src/googleWeb");
      const lang = typeof navigator !== "undefined" && navigator.language?.startsWith("it") ? "it" : "es";
      const token = await googleWebIdToken(GOOGLE_WEB_CLIENT_ID, lang, lang === "it" ? "Annulla" : "Cancelar");
      if (!token) return; // el usuario cerro la ventana
      await applySession(await api<{ session_token: string; user: User }>("/auth/google", { body: { id_token: token } }));
      return;
    }
    const { GoogleSignin, isSuccessResponse } = await import("@react-native-google-signin/google-signin");
    GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID });
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const response = await GoogleSignin.signIn();
    if (!isSuccessResponse(response)) return; // el usuario cancelo
    const idToken = response.data.idToken;
    if (!idToken) throw new Error("Google no devolvio el token.");
    await applySession(
      await api<{ session_token: string; user: User }>("/auth/google", { body: { id_token: idToken } }),
    );
  }, [applySession]);

  // Cambia la contraseña con el código recibido por email y deja la sesión iniciada.
  const resetPassword = useCallback(
    async (email: string, code: string, newPassword: string) => {
      await applySession(await api("/auth/reset-password", { body: { email, code, new_password: newPassword } }));
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    if (Platform.OS !== "web") {
      try {
        const { GoogleSignin } = await import("@react-native-google-signin/google-signin");
        await GoogleSignin.signOut();
      } catch {}
    }
    await clear();
  }, [clear]);

  const refreshUser = useCallback(async () => {
    const fresh = await api<User>("/auth/me");
    setUser(fresh);
    remember(fresh);
  }, [remember]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, loginWithGoogle, resetPassword, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);