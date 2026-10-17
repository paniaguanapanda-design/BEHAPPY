import { Platform } from "react-native";
import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { usesNativeTabs } from "@/src/navigation";
import { useI18n } from "@/src/i18n";
import { useTheme } from "@/src/theme";

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
        <NativeTabs.Trigger name="specialists">
          <NativeTabs.Trigger.Icon sf="person.2.fill" />
          <NativeTabs.Trigger.Label>{t("tab_specialists")}</NativeTabs.Trigger.Label>
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

  const icon = (on: React.ComponentProps<typeof Ionicons>["name"], off: React.ComponentProps<typeof Ionicons>["name"]) => {
    const TabIcon = ({ focused, color }: { focused: boolean; color: import("react-native").ColorValue }) => (
      <Ionicons name={focused ? on : off} size={24} color={color as string} />
    );
    return TabIcon;
  };

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t("tab_scan"), tabBarButtonTestID: "tab-scan", tabBarIcon: icon("scan-circle", "scan-circle-outline") }} />
      <Tabs.Screen name="specialists" options={{ title: t("tab_specialists"), tabBarButtonTestID: "tab-specialists", tabBarIcon: icon("people", "people-outline") }} />
      <Tabs.Screen name="messages" options={{ title: t("tab_messages"), tabBarButtonTestID: "tab-messages", tabBarIcon: icon("chatbubbles", "chatbubbles-outline") }} />
      <Tabs.Screen name="profile" options={{ title: t("tab_profile"), tabBarButtonTestID: "tab-profile", tabBarIcon: icon("person-circle", "person-circle-outline") }} />
    </Tabs>
  );
}
