import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { usesNativeTabs } from "@/src/navigation";
import { useI18n } from "@/src/i18n";
import { useTheme } from "@/src/theme";
import { AppTabBar } from "@/src/TabBar";

export default function TabsLayout() {
  const { t } = useI18n();
  const { colors } = useTheme();

  if (usesNativeTabs) {
    return (
      <NativeTabs tintColor={colors.brandPrimary}>
        <NativeTabs.Trigger name="index">
          <NativeTabs.Trigger.Icon sf="camera.viewfinder" />
          <NativeTabs.Trigger.Label>{t("tab_scan")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="requests">
          <NativeTabs.Trigger.Icon sf="doc.text" />
          <NativeTabs.Trigger.Label>{t("tab_requests")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="specialists">
          <NativeTabs.Trigger.Icon sf="person.2.fill" />
          <NativeTabs.Trigger.Label>{t("tab_specialists")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="ferreterias">
          <NativeTabs.Trigger.Icon sf="storefront.fill" />
          <NativeTabs.Trigger.Label>{t("tab_stores")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="messages">
          <NativeTabs.Trigger.Icon sf="bubble.left.and.bubble.right.fill" />
          <NativeTabs.Trigger.Label>{t("tab_messages")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="profile">
          <NativeTabs.Trigger.Icon sf="person.crop.circle" />
          <NativeTabs.Trigger.Label>{t("tab_profile")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
      </NativeTabs>
    );
  }

  return (
    <Tabs tabBar={(props) => <AppTabBar {...props} />} screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="index" options={{ title: t("tab_home"), tabBarButtonTestID: "tab-home" }} />
      <Tabs.Screen name="requests" options={{ title: t("tab_requests"), tabBarButtonTestID: "tab-requests" }} />
      <Tabs.Screen name="specialists" options={{ title: t("tab_specialists"), tabBarButtonTestID: "tab-specialists" }} />
      <Tabs.Screen name="ferreterias" options={{ title: t("tab_stores"), tabBarButtonTestID: "tab-stores" }} />
      <Tabs.Screen name="messages" options={{ title: t("tab_messages"), tabBarButtonTestID: "tab-messages" }} />
      <Tabs.Screen name="profile" options={{ title: t("tab_profile"), tabBarButtonTestID: "tab-profile" }} />
    </Tabs>
  );
}
