import { useEffect } from "react";
import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { router } from "expo-router";
import { api } from "@/src/api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }),
});

async function sendToken(lang: string) {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "BeHappy",
      importance: Notifications.AndroidImportance.HIGH,
      lightColor: "#FF6B00",
    });
  }
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  const { data } = await Notifications.getExpoPushTokenAsync(projectId ? { projectId } : undefined);
  await api("/push/token", { body: { token: data, lang } });
}

// Asks for permission (only when it makes sense: sending a message, turning alerts on) and registers the phone.
export async function enablePush(lang: string): Promise<boolean> {
  if (Platform.OS === "web") return false;
  try {
    let p = await Notifications.getPermissionsAsync();
    if (!p.granted && p.canAskAgain) p = await Notifications.requestPermissionsAsync();
    if (!p.granted) return false;
    await sendToken(lang);
    return true;
  } catch {
    return false;
  }
}

export async function pushAllowed(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  try {
    return (await Notifications.getPermissionsAsync()).granted;
  } catch {
    return false;
  }
}

// Signed in: refresh the token if permission was already given, and open the chat when a notification is tapped.
export function usePushSetup(userId: string | null, lang: string) {
  useEffect(() => {
    if (!userId || Platform.OS === "web") return;
    pushAllowed().then((ok) => {
      if (ok) sendToken(lang).catch(() => {});
    });
    const open = (data: any) => {
      if (data?.conversation_id) router.push({ pathname: "/chat/[id]", params: { id: String(data.conversation_id) } });
      else if (data?.type === "nearby") router.push("/pro-stats");
    };
    // Opened from a notification while closed: wait for the welcome screen to finish first.
    const first = setTimeout(
      () => Notifications.getLastNotificationResponseAsync().then((r) => r && open(r.notification.request.content.data)),
      1800,
    );
    const sub = Notifications.addNotificationResponseReceivedListener((r) => open(r.notification.request.content.data));
    return () => {
      clearTimeout(first);
      sub.remove();
    };
  }, [userId, lang]);
}
