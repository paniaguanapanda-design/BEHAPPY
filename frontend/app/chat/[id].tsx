import React, { useEffect, useRef, useState } from "react";
import { FlatList, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { Image } from "expo-image";
import { api, imageSource } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { fonts, makeStyles, useTheme } from "@/src/theme";
import { Avatar, Button } from "@/src/ui";
import { timeLabel } from "@/src/time";
import { queryClient } from "@/src/query-client";
import { ReportSheet, SPECIALIST_REASONS } from "@/src/ReportSheet";
import { enablePush } from "@/src/push";
import { useSeen } from "@/src/seen";
import { NewBadge } from "@/src/proUi";

export default function Chat() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const toast = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const conv = useQuery({ queryKey: ["conversation", id], queryFn: () => api<any>(`/conversations/${id}`) });
  const msgs = useQuery({ queryKey: ["messages", id], queryFn: () => api<any[]>(`/conversations/${id}/messages`), refetchInterval: 3000 });
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const list = useRef<FlatList>(null);
  const [report, setReport] = useState<null | { type: string; id: string }>(null);
  const [stars, setStars] = useState(0);
  const isSpecialist = !!user?.specialist_id;
  const settings = useQuery({
    queryKey: ["pro-settings", lang],
    queryFn: () => api<any>(`/specialists/me/settings?lang=${lang}`),
    enabled: isSpecialist,
  });
  const seenWhere = useSeen("chat_where_buy");

  const c = conv.data;
  const iAmClient = c?.client_id === user?.user_id;
  const otherName = c ? (iAmClient ? c.specialist_name : c.client_name) : "";
  const otherPic = c ? (iAmClient ? c.specialist_avatar : c.client_picture) : null;
  const otherUserId = c ? (iAmClient ? c.specialist_user_id : c.client_id) : "";

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
      enablePush(lang); // replies arrive as phone notifications (asks only the first time)
      msgs.refetch();
      queryClient.invalidateQueries({ queryKey: ["specialist"] });
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="chat-back-button" onPress={() => router.back()} style={styles.backRound} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
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
        <Pressable testID="chat-report-button" onPress={() => c && setReport(iAmClient ? { type: "specialist", id: c.specialist_id } : { type: "user", id: otherUserId })} style={styles.back} hitSlop={8}>
          <Ionicons name="ellipsis-vertical" size={22} color={colors.onSurface} />
        </Pressable>
      </View>
      <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }}>
        <FlatList
          ref={list}
          data={msgs.data || []}
          keyExtractor={(m) => m.message_id}
          contentContainerStyle={{ padding: 16, gap: 8 }}
          onContentSizeChange={() => list.current?.scrollToEnd({ animated: false })}
          ListHeaderComponent={
            c?.diagnosis ? (
              <View style={styles.dcard} testID="chat-diagnosis-card">
                {c.diagnosis.image_path ? <Image source={imageSource(c.diagnosis.image_path)} style={styles.dimg} contentFit="cover" /> : null}
                <View style={styles.dbody}>
                  <Text style={styles.dlabel}>{t("ai_diagnosis")}</Text>
                  <Text style={styles.dtitle}>{(lang === "it" ? c.diagnosis.title_it : c.diagnosis.title_es) || c.diagnosis.title_it}</Text>
                  {c.diagnosis.materials?.length ? (
                    <>
                      <Text style={styles.dmat}>
                        {t("needs")}: {c.diagnosis.materials.join(", ")}
                      </Text>
                      <Pressable
                        testID="chat-where-buy"
                        onPress={() => {
                          seenWhere.markSeen();
                          router.push({ pathname: "/stores", params: { category: c.diagnosis.category } });
                        }}
                        style={({ pressed }) => [styles.where, pressed && { opacity: 0.85 }]}
                      >
                        <Ionicons name="construct" size={15} color={colors.onBrandSecondary} />
                        <Text style={styles.whereText}>
                          {c.stores_nearby ? t("where_buy").replace("{n}", String(c.stores_nearby)) : t("where_buy_search")} ›
                        </Text>
                        {seenWhere.isNew ? <NewBadge /> : null}
                      </Pressable>
                    </>
                  ) : null}
                </View>
              </View>
            ) : null
          }
          renderItem={({ item }) => {
            const mine = item.sender_id === user?.user_id;
            return (
              <Pressable onLongPress={() => !mine && setReport({ type: "message", id: item.message_id })} delayLongPress={400} style={[styles.bubble, mine ? styles.mine : styles.theirs]} testID={`message-${item.message_id}`}>
                <Text style={[styles.msg, mine && { color: colors.onSurfaceInverse }]}>{item.text}</Text>
                <Text style={[styles.time, mine && { color: colors.onSurfaceInverse }]}>{timeLabel(item.created_at, lang)}</Text>
              </Pressable>
            );
          }}
        />
        {iAmClient && c?.review_prompt ? (
          <View style={styles.review} testID="chat-review-card">
            <Text style={styles.reviewTitle}>{t("how_did_it_go").replace("{name}", (c.specialist_name || "").split(" ")[0])}</Text>
            <View style={styles.starsRow}>
              {[1, 2, 3, 4, 5].map((n) => (
                <Pressable key={n} testID={`chat-star-${n}`} onPress={() => setStars(n)} hitSlop={4}>
                  <Ionicons name={n <= stars ? "star" : "star-outline"} size={30} color={colors.brandPrimary} />
                </Pressable>
              ))}
            </View>
            <View style={styles.reviewBtns}>
              <Pressable
                testID="chat-leave-review"
                onPress={() =>
                  router.push({ pathname: "/specialist/[id]", params: { id: c.specialist_id, review: String(stars || 5) } })
                }
                style={({ pressed }) => [styles.reviewBtn, { backgroundColor: colors.brandPrimary }, pressed && { transform: [{ scale: 0.97 }] }]}
              >
                <Text style={[styles.reviewBtnText, { color: colors.onBrandPrimary }]} numberOfLines={1}>
                  {t("leave_review")}
                </Text>
              </Pressable>
              <Pressable
                testID="chat-report-problem"
                onPress={() => setReport({ type: "specialist", id: c.specialist_id })}
                style={({ pressed }) => [styles.reviewBtn, { backgroundColor: colors.surfaceTertiary }, pressed && { transform: [{ scale: 0.97 }] }]}
              >
                <Text style={[styles.reviewBtnText, { color: colors.error }]} numberOfLines={1}>
                  {t("report_problem")}
                </Text>
              </Pressable>
            </View>
          </View>
        ) : null}
        {!iAmClient && c?.specialist_can_reply !== false && settings.data?.quick_replies?.length ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.qrBar} contentContainerStyle={styles.qrContent} keyboardShouldPersistTaps="always">
            {settings.data.quick_replies.map((r: string, i: number) => (
              <Pressable key={`${i}-${r}`} testID={`quick-reply-${i}`} onPress={() => setText(r)} style={({ pressed }) => [styles.qr, pressed && { opacity: 0.8 }]}>
                {i === 0 ? <Ionicons name="flash" size={13} color={colors.onBrandSecondary} /> : null}
                <Text style={styles.qrText}>{r}</Text>
              </Pressable>
            ))}
          </ScrollView>
        ) : null}
        {!iAmClient && c?.specialist_can_reply === false ? (
          <View style={[styles.lockBar, { paddingBottom: insets.bottom + 12 }]} testID="chat-membership-required">
            <View style={styles.lockRow}>
              <Text style={styles.lockEmoji}>⏸️</Text>
              <Text style={[styles.lockText, { flex: 1 }]}>{t("reply_needs_membership")}</Text>
            </View>
          </View>
        ) : (
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
            <Ionicons name="send" size={19} color={colors.onBrandPrimary} />
          </Pressable>
        </View>
        )}
      </KeyboardAvoidingView>
      <ReportSheet
        visible={!!report}
        onClose={() => setReport(null)}
        targetType={report?.type ?? "user"}
        targetId={report?.id ?? ""}
        blockUserId={otherUserId}
        onBlocked={() => router.back()}
        reasons={report?.type === "specialist" ? SPECIALIST_REASONS : undefined}
        targetName={report?.type === "specialist" ? c?.specialist_name : undefined}
      />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 8, paddingBottom: 10, backgroundColor: c.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: c.border },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  backRound: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center", marginLeft: 4 },
  dcard: { alignSelf: "flex-start", width: "84%", backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 16, overflow: "hidden", marginBottom: 8 },
  dimg: { width: "100%", height: 90, backgroundColor: c.surfaceTertiary },
  dbody: { padding: 12, gap: 4 },
  dlabel: { fontSize: 12, color: c.muted },
  dtitle: { fontSize: 16, fontFamily: fonts.display, color: c.onSurface },
  dmat: { fontSize: 13, color: c.onSurfaceTertiary, lineHeight: 18 },
  where: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: c.brandSecondary, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, marginTop: 4 },
  whereText: { flex: 1, fontSize: 13, fontWeight: "700", color: c.onBrandSecondary },
  review: { marginHorizontal: 16, marginBottom: 10, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 18, padding: 14, alignItems: "center", gap: 8 },
  reviewTitle: { fontSize: 17, fontFamily: fonts.display, color: c.onSurface, textAlign: "center" },
  starsRow: { flexDirection: "row", gap: 8 },
  reviewBtns: { flexDirection: "row", gap: 8, alignSelf: "stretch" },
  reviewBtn: { flex: 1, minHeight: 44, borderRadius: 999, alignItems: "center", justifyContent: "center", paddingHorizontal: 8 },
  reviewBtnText: { fontSize: 14, fontWeight: "700" },
  qrBar: { flexGrow: 0, backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border },
  qrContent: { paddingHorizontal: 12, paddingVertical: 8, gap: 8 },
  qr: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: c.brandSecondary, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8 },
  qrText: { fontSize: 13, fontWeight: "600", color: c.onBrandSecondary },
  headInfo: { flex: 1, flexDirection: "row", alignItems: "center", gap: 10 },
  headName: { fontSize: 17, fontWeight: "700", color: c.onSurface, flex: 1 },
  bubble: { maxWidth: "80%", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 18, gap: 2 },
  mine: { alignSelf: "flex-end", backgroundColor: c.surfaceInverse, borderBottomRightRadius: 6 },
  theirs: { alignSelf: "flex-start", backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderBottomLeftRadius: 6 },
  msg: { fontSize: 15, color: c.onSurface, lineHeight: 21 },
  time: { fontSize: 10, color: c.muted, alignSelf: "flex-end", opacity: 0.8 },
  timeDark: { fontSize: 10, color: c.onBrandSecondary, alignSelf: "flex-end" },
  reqCard: { maxWidth: "85%", padding: 14, borderRadius: 14, backgroundColor: c.brandSecondary, borderWidth: 1, borderColor: c.brandTertiary, gap: 6 },
  reqHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  reqTitle: { fontWeight: "800", color: c.onBrandSecondary, fontSize: 13 },
  reqText: { color: c.onBrandSecondary, fontSize: 14, lineHeight: 20 },
  lockBar: { gap: 10, paddingHorizontal: 16, paddingTop: 12, backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border },
  lockRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  lockEmoji: { fontSize: 20 },
  lockText: { fontSize: 14, color: c.onSurfaceTertiary, lineHeight: 20 },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: 8, paddingHorizontal: 12, paddingTop: 8, backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border },
  input: { flex: 1, minHeight: 44, maxHeight: 120, borderRadius: 22, backgroundColor: c.surfaceTertiary, paddingHorizontal: 16, paddingTop: 12, paddingBottom: 12, fontSize: 15, color: c.onSurface },
  send: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  quoteBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  sysMsg: { alignSelf: "center", flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.surfaceTertiary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999 },
  sysText: { fontSize: 12, color: c.onSurfaceTertiary, fontWeight: "600" },
}));
