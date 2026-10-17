import React from "react";
import { FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";
import { Button } from "@/src/ui";

export default function Requests() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const q = useQuery({ queryKey: ["requests"], queryFn: () => api<any[]>("/requests") });

  const statusColor: Record<string, string> = {
    pending: colors.warning, accepted: colors.info, completed: colors.success, rejected: colors.error, cancelled: colors.muted,
  };

  const update = async (rid: string, status: string) => {
    try {
      await api(`/requests/${rid}`, { method: "PATCH", body: { status } });
      q.refetch();
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="requests-back-button" onPress={() => router.back()} style={styles.back}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("requests_title")}</Text>
      </View>
      <FlatList
        data={q.data || []}
        keyExtractor={(r) => r.request_id}
        contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: insets.bottom + 24 }}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={q.refetch} tintColor={colors.brandPrimary} />}
        ListEmptyComponent={
          q.isLoading ? null : (
            <View style={styles.empty} testID="no-requests">
              <Ionicons name="clipboard-outline" size={40} color={colors.brandTertiary} />
              <Text style={styles.muted}>{t("no_requests")}</Text>
            </View>
          )
        }
        renderItem={({ item }) => {
          const asSpec = item.specialist_user_id === user?.user_id;
          return (
            <View style={styles.card} testID={`request-card-${item.request_id}`}>
              <View style={styles.topRow}>
                <Text style={styles.who} numberOfLines={1}>
                  {asSpec ? `${t("from")}: ${item.client_name}` : `${t("to")}: ${item.specialist_name}`}
                </Text>
                <View style={[styles.status, { backgroundColor: statusColor[item.status] }]}>
                  <Text style={styles.statusText} testID={`request-status-${item.request_id}`}>
                    {t(`st_${item.status}`)}
                  </Text>
                </View>
              </View>
              {item.diagnosis_title ? <Text style={styles.diag}>{item.diagnosis_title}</Text> : null}
              <Text style={styles.desc}>{item.description}</Text>
              {item.address || item.preferred_date ? (
                <Text style={styles.muted}>
                  {[item.address, item.preferred_date].filter(Boolean).join(" · ")}
                </Text>
              ) : null}
              <View style={styles.actions}>
                <Button
                  variant="ghost"
                  icon="chatbubble-outline"
                  title={t("open_chat")}
                  style={styles.actionBtn}
                  onPress={() => router.push({ pathname: "/chat/[id]", params: { id: item.conversation_id } })}
                  testID={`request-chat-${item.request_id}`}
                />
                {asSpec && item.status === "pending" && (
                  <>
                    <Button title={t("accept")} style={styles.actionBtn} onPress={() => update(item.request_id, "accepted")} testID={`request-accept-${item.request_id}`} />
                    <Button variant="danger" title={t("reject")} style={styles.actionBtn} onPress={() => update(item.request_id, "rejected")} testID={`request-reject-${item.request_id}`} />
                  </>
                )}
                {asSpec && item.status === "accepted" && (
                  <Button title={t("complete")} style={styles.actionBtn} onPress={() => update(item.request_id, "completed")} testID={`request-complete-${item.request_id}`} />
                )}
                {!asSpec && item.status === "pending" && (
                  <Button variant="danger" title={t("cancel")} style={styles.actionBtn} onPress={() => update(item.request_id, "cancelled")} testID={`request-cancel-${item.request_id}`} />
                )}
                {!asSpec && item.status === "completed" && (
                  <Button
                    title={t("rate_now")}
                    icon="star"
                    style={styles.actionBtn}
                    onPress={() => router.push({ pathname: "/specialist/[id]", params: { id: item.specialist_id } })}
                    testID={`request-rate-${item.request_id}`}
                  />
                )}
              </View>
            </View>
          );
        }}
      />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: c.divider },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  empty: { alignItems: "center", padding: 32, gap: 12 },
  muted: { color: c.muted, fontSize: 13 },
  card: { padding: 16, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 8 },
  topRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  who: { fontSize: 16, fontWeight: "700", color: c.onSurface, flex: 1 },
  status: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  statusText: { color: c.onSuccess, fontSize: 12, fontWeight: "700" },
  diag: { fontSize: 13, fontWeight: "700", color: c.brandTertiary },
  desc: { fontSize: 15, color: c.onSurfaceTertiary, lineHeight: 21 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  actionBtn: { minHeight: 42, flexGrow: 1 },
}));
