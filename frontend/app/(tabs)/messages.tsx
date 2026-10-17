import React from "react";
import { FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";
import { Avatar } from "@/src/ui";

import { timeLabel } from "@/src/time";

export default function Messages() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useI18n();
  const q = useQuery({ queryKey: ["conversations"], queryFn: () => api<any[]>("/conversations"), refetchInterval: 5000 });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>{t("messages_title")}</Text>
      </View>
      <FlatList
        data={q.data || []}
        keyExtractor={(c) => c.conversation_id}
        contentContainerStyle={{ paddingBottom: bottomChrome + 24, flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
        ListEmptyComponent={
          q.isLoading ? null : (
            <View style={styles.empty} testID="no-conversations">
              <Ionicons name="chatbubbles-outline" size={44} color={colors.brandTertiary} />
              <Text style={styles.emptyText}>{t("no_messages")}</Text>
            </View>
          )
        }
        renderItem={({ item }) => {
          const iAmClient = item.client_id === user?.user_id;
          const name = iAmClient ? item.specialist_name : item.client_name;
          const pic = iAmClient ? item.specialist_avatar : item.client_picture;
          const unread = item.unread?.[user?.user_id ?? ""] ?? 0;
          return (
            <Pressable
              testID={`conversation-item-${item.conversation_id}`}
              onPress={() => router.push({ pathname: "/chat/[id]", params: { id: item.conversation_id } })}
              style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surfaceTertiary }]}
            >
              <Avatar uri={pic} name={name} size={52} />
              <View style={{ flex: 1, gap: 2 }}>
                <View style={styles.topLine}>
                  <Text style={styles.name} numberOfLines={1}>
                    {name}
                  </Text>
                  <Text style={styles.time}>{timeLabel(item.updated_at)}</Text>
                </View>
                <View style={styles.topLine}>
                  <Text style={[styles.last, unread > 0 && styles.lastUnread]} numberOfLines={1}>
                    {item.last_message?.replace("[REQUEST] ", `${t("service_request")}: `) || "…"}
                  </Text>
                  {unread > 0 && (
                    <View style={styles.badge}>
                      <Text style={styles.badgeText}>{unread}</Text>
                    </View>
                  )}
                </View>
              </View>
            </Pressable>
          );
        }}
      />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 24, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontSize: 28, fontWeight: "800", color: c.onSurface, letterSpacing: -0.6 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", padding: 32, gap: 12 },
  emptyText: { color: c.muted, textAlign: "center", fontSize: 15, lineHeight: 22 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: c.divider },
  topLine: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  name: { fontSize: 16, fontWeight: "700", color: c.onSurface, flex: 1 },
  time: { fontSize: 12, color: c.muted },
  last: { fontSize: 14, color: c.muted, flex: 1 },
  lastUnread: { color: c.onSurface, fontWeight: "600" },
  badge: { minWidth: 22, height: 22, borderRadius: 11, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: 6 },
  badgeText: { color: c.onBrandPrimary, fontSize: 12, fontWeight: "700" },
}));
