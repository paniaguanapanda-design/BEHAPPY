import React, { useEffect, useRef, useState } from "react";
import { FlatList, Pressable, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";
import { Avatar } from "@/src/ui";
import { timeLabel } from "@/src/time";

export default function Chat() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const conv = useQuery({ queryKey: ["conversation", id], queryFn: () => api<any>(`/conversations/${id}`) });
  const msgs = useQuery({ queryKey: ["messages", id], queryFn: () => api<any[]>(`/conversations/${id}/messages`), refetchInterval: 3000 });
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const list = useRef<FlatList>(null);

  const c = conv.data;
  const iAmClient = c?.client_id === user?.user_id;
  const otherName = c ? (iAmClient ? c.specialist_name : c.client_name) : "";
  const otherPic = c ? (iAmClient ? c.specialist_avatar : c.client_picture) : null;

  useEffect(() => {
    setTimeout(() => list.current?.scrollToEnd({ animated: true }), 100);
  }, [msgs.data?.length]);

  const send = async () => {
    const v = text.trim();
    if (!v) return;
    setSending(true);
    try {
      await api(`/conversations/${id}/messages`, { body: { text: v } });
      setText("");
      msgs.refetch();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="chat-back-button" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Pressable
          style={styles.headInfo}
          disabled={!iAmClient}
          onPress={() => c && router.push({ pathname: "/specialist/[id]", params: { id: c.specialist_id } })}
          testID="chat-header-profile"
        >
          <Avatar uri={otherPic} name={otherName} size={38} />
          <Text style={styles.headName} numberOfLines={1} testID="chat-header-name">
            {otherName}
          </Text>
        </Pressable>
        <Pressable testID="chat-requests-button" onPress={() => router.push("/requests")} style={styles.back} hitSlop={8}>
          <Ionicons name="clipboard-outline" size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }}>
        <FlatList
          ref={list}
          data={msgs.data || []}
          keyExtractor={(m) => m.message_id}
          contentContainerStyle={{ padding: 16, gap: 8 }}
          onContentSizeChange={() => list.current?.scrollToEnd({ animated: false })}
          renderItem={({ item }) => {
            const mine = item.sender_id === user?.user_id;
            if (item.kind === "request")
              return (
                <View style={[styles.reqCard, mine ? { alignSelf: "flex-end" } : { alignSelf: "flex-start" }]} testID={`message-${item.message_id}`}>
                  <View style={styles.reqHead}>
                    <Ionicons name="clipboard" size={16} color={colors.onBrandSecondary} />
                    <Text style={styles.reqTitle}>{t("service_request")}</Text>
                  </View>
                  <Text style={styles.reqText}>{item.text.replace("[REQUEST] ", "")}</Text>
                  <Text style={styles.timeDark}>{timeLabel(item.created_at)}</Text>
                </View>
              );
            return (
              <View style={[styles.bubble, mine ? styles.mine : styles.theirs]} testID={`message-${item.message_id}`}>
                <Text style={[styles.msg, mine && { color: colors.onBrandPrimary }]}>{item.text}</Text>
                <Text style={[styles.time, mine && { color: colors.onBrandPrimary }]}>{timeLabel(item.created_at)}</Text>
              </View>
            );
          }}
        />
        <View style={[styles.inputBar, { paddingBottom: insets.bottom + 8 }]}>
          <TextInput
            testID="chat-message-input"
            style={styles.input}
            placeholder={t("type_message")}
            placeholderTextColor={colors.muted}
            value={text}
            onChangeText={setText}
            multiline
          />
          <Pressable testID="chat-send-button" onPress={send} disabled={sending || !text.trim()} style={[styles.send, (!text.trim() || sending) && { opacity: 0.5 }]}>
            <Ionicons name="arrow-up" size={22} color={colors.onBrandPrimary} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 8, paddingBottom: 10, backgroundColor: c.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: c.border },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headInfo: { flex: 1, flexDirection: "row", alignItems: "center", gap: 10 },
  headName: { fontSize: 17, fontWeight: "700", color: c.onSurface, flex: 1 },
  bubble: { maxWidth: "80%", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 18, gap: 2 },
  mine: { alignSelf: "flex-end", backgroundColor: c.brandPrimary, borderBottomRightRadius: 6 },
  theirs: { alignSelf: "flex-start", backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderBottomLeftRadius: 6 },
  msg: { fontSize: 15, color: c.onSurface, lineHeight: 21 },
  time: { fontSize: 10, color: c.muted, alignSelf: "flex-end", opacity: 0.8 },
  timeDark: { fontSize: 10, color: c.onBrandSecondary, alignSelf: "flex-end" },
  reqCard: { maxWidth: "85%", padding: 14, borderRadius: 14, backgroundColor: c.brandSecondary, borderWidth: 1, borderColor: c.brandTertiary, gap: 6 },
  reqHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  reqTitle: { fontWeight: "800", color: c.onBrandSecondary, fontSize: 13 },
  reqText: { color: c.onBrandSecondary, fontSize: 14, lineHeight: 20 },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: 8, paddingHorizontal: 12, paddingTop: 8, backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border },
  input: { flex: 1, minHeight: 44, maxHeight: 120, borderRadius: 22, backgroundColor: c.surfaceTertiary, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 12, fontSize: 15, color: c.onSurface },
  send: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
}));
