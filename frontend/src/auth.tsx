import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import { api, setToken, setUnauthorizedHandler } from "@/src/api";
import { storage } from "@/src/utils/storage";

const TOKEN_KEY = "auth_token";
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
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<Ctx>(null as unknown as Ctx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const clear = useCallback(async () => {
    await storage.secureRemove(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const applySession = useCallback(async (res: { session_token: string; user: User }) => {
    await storage.secureSet(TOKEN_KEY, res.session_token);
    setToken(res.session_token);
    setUser(res.user);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clear();
    });
    (async () => {
      try {
        const stored = await storage.secureGet(TOKEN_KEY, null);
        if (typeof stored === "string" && stored) {
          setToken(stored);
          try {
            setUser(await api<User>("/auth/me"));
          } catch {
            await clear();
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [clear]);

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
    if (Platform.OS === "web") {
      window.alert("El acceso con Google solo esta disponible en la app de Android.");
      return;
    }
    if (!GOOGLE_WEB_CLIENT_ID) throw new Error("Google no esta configurado.");
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
    setUser(await api<User>("/auth/me"));
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, loginWithGoogle, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);