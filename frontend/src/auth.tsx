import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { api, setToken, setUnauthorizedHandler } from "@/src/api";
import { storage } from "@/src/utils/storage";

WebBrowser.maybeCompleteAuthSession();

const TOKEN_KEY = "auth_token";

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

const extractSessionId = (url?: string | null) => {
  if (!url) return null;
  const m = url.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const sent = useRef(new Set<string>());

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

  const exchange = useCallback(
    async (sessionId: string) => {
      if (sent.current.has(sessionId)) return false;
      sent.current.add(sessionId);
      const res = await api<{ session_token: string; user: User }>("/auth/session", { body: { session_id: sessionId } });
      await applySession(res);
      return true;
    },
    [applySession],
  );

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clear();
    });
    (async () => {
      try {
        let sid: string | null = null;
        if (Platform.OS === "web" && typeof window !== "undefined") {
          sid = extractSessionId(window.location.hash) || extractSessionId(window.location.search);
        } else {
          sid = extractSessionId(await Linking.getInitialURL());
        }
        if (sid) {
          try {
            await exchange(sid);
            if (Platform.OS === "web") window.history.replaceState(window.history.state, "", window.location.pathname);
            return;
          } catch {}
        }
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
    if (Platform.OS === "web") return;
    const sub = Linking.addEventListener("url", ({ url }) => {
      const sid = extractSessionId(url);
      if (sid) exchange(sid).catch(() => {});
    });
    return () => sub.remove();
  }, [clear, exchange]);

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
    const redirectUrl = Platform.OS === "web" ? window.location.origin + "/" : Linking.createURL("");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    if (Platform.OS === "web") {
      window.location.href = authUrl;
      return;
    }
    let captured: string | null = null;
    const sub = Linking.addEventListener("url", ({ url }) => {
      captured = url;
    });
    try {
      const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
      const url = (result.type === "success" ? result.url : null) || captured || (await Linking.getInitialURL());
      const sid = extractSessionId(url);
      if (sid) await exchange(sid);
    } finally {
      sub.remove();
    }
  }, [exchange]);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
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
