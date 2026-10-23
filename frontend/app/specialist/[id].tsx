import React, { useState } from "react";
import { Linking, Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { BlurView } from "expo-blur";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api, imageUri } from "@/src/api";
import { useAuth } from "@/src/auth";
import { captionFor, tradesLabel, useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme } from "@/src/theme";
import { Avatar, Button, Loading, SectionTitle, Stars, VerifiedBadge } from "@/src/ui";

export default function SpecialistProfile() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const toast = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const sq = useQuery({ queryKey: ["specialist", id], queryFn: () => api<any>(`/specialists/${id}`) });
  const rq = useQuery({ queryKey: ["reviews", id], queryFn: () => api<any[]>(`/specialists/${id}/reviews`) });
  const [sheet, setSheet] = useState<null | "review">(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  if (sq.isLoading) return <Loading />;
  const s = sq.data;
  if (!s)
    return (
      <View style={[styles.root, { alignItems: "center", justifyContent: "center", gap: 12 }]}>
        <Text style={styles.body}>{t("error_generic")}</Text>
        <Button title={t("back")} onPress={() => router.back()} testID="specialist-error-back" />
      </View>
    );

  const isMe = s.user_id === user?.user_id;
  const heroImg = s.portfolio?.[0]?.image; // cover is always a work photo, never a personal photo

  const openChat = async () => {
    try {
      const c = await api<any>("/conversations", { body: { specialist_id: s.specialist_id } });
      router.push({ pathname: "/chat/[id]", params: { id: c.conversation_id } });
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const sendReview = async () => {
    if (!rating) return toast(t("required"), "error");
    setBusy(true);
    try {
      await api(`/specialists/${s.specialist_id}/reviews`, { body: { rating, comment } });
      setSheet(null);
      setComment("");
      toast(t("review_sent"));
      sq.refetch();
      rq.refetch();
      queryClient.invalidateQueries({ queryKey: ["specialists"] });
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 110 }}>
        <View style={styles.hero}>
          {heroImg ? <Image source={{ uri: imageUri(heroImg) }} style={styles.abs} contentFit="cover" /> : <View style={[styles.abs, { backgroundColor: colors.brandPrimary }]} />}
          <LinearGradient colors={["transparent", colors.surfaceInverse]} style={styles.abs} />
          <Pressable testID="specialist-back-button" onPress={() => router.back()} style={[styles.back, { top: insets.top + 8 }]}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurfaceInverse} />
          </Pressable>
          <View style={styles.heroContent}>
            <View style={{ flex: 1, gap: 6 }}>
              <Text style={styles.name} testID="specialist-name">
                {s.name}
              </Text>
              <Text style={styles.heroSub} testID="specialist-trades">
                {tradesLabel(s.categories, t)} · {t("turin")}
              </Text>
              {s.subtrades?.length ? (
                <Text style={styles.heroSub} testID="specialist-subtrades">
                  {s.subtrades.map((x: string) => t(`sub_${x}`)).join(", ")}
                </Text>
              ) : null}
              {s.verified && <VerifiedBadge label={t("verified")} />}
            </View>
          </View>
        </View>

        {s.rating_avg != null && (
          <View style={styles.stats}>
            <View style={styles.stat}>
              <Text style={styles.statVal} testID="specialist-rating">
                {s.rating_avg.toFixed(1).replace(".", ",")}
              </Text>
              <Stars value={s.rating_avg} size={14} />
              <Text style={styles.statLabel}>
                {s.reviews_count} {t("ratings")}
              </Text>
            </View>
          </View>
        )}

        <View style={styles.content}>
          {isMe && !s.membership_active && (
            <View style={styles.hiddenBanner} testID="hidden-profile-banner">
              <Text style={styles.body}>{t("hidden_profile")}</Text>
              <Button title={t("activate_membership")} icon="ribbon" onPress={() => router.push("/membership")} testID="activate-membership-button" />
            </View>
          )}
          {isMe && s.membership_active && !s.portfolio?.length && (
            <View style={styles.hiddenBanner} testID="need-photos-banner">
              <Text style={styles.body}>{t("need_photos")}</Text>
            </View>
          )}
          {s.bio ? (
            <View style={{ gap: 8 }}>
              <SectionTitle>{t("about")}</SectionTitle>
              <Text style={styles.body}>{s.bio}</Text>
            </View>
          ) : null}

          <View style={{ gap: 12 }}>
            <SectionTitle>{t("portfolio")}</SectionTitle>
            {s.portfolio?.length ? (
              <View style={styles.grid}>
                {s.portfolio.map((p: any) => (
                  <Pressable key={p.item_id} testID={`portfolio-item-${p.item_id}`} onPress={() => setPreview(p.image)} style={styles.gridItem}>
                    <Image source={{ uri: imageUri(p.image) }} style={styles.gridImg} contentFit="cover" />
                    <Text style={styles.caption} numberOfLines={1}>
                      {captionFor(p, lang)}
                    </Text>
                  </Pressable>
                ))}
              </View>
            ) : (
              <Text style={styles.muted}>{t("no_portfolio")}</Text>
            )}
          </View>

          <View style={{ gap: 12 }}>
            <SectionTitle>{t("reviews_title")}</SectionTitle>
            {s.can_review && <Button variant="secondary" icon="star-outline" title={t("rate_specialist")} onPress={() => setSheet("review")} testID="write-review-button" />}
            {rq.data?.length === 0 && <Text style={styles.muted}>{t("no_reviews")}</Text>}
            {rq.data?.map((r) => (
              <View key={r.review_id} style={styles.review} testID={`review-${r.review_id}`}>
                <View style={styles.reviewHead}>
                  <Avatar name={r.user_name} size={36} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.reviewName}>{r.user_name}</Text>
                    <Stars value={r.rating} size={12} />
                  </View>
                </View>
                {r.comment ? <Text style={styles.body}>{(lang === "it" ? r.comment_it : r.comment_es) || r.comment}</Text> : null}
              </View>
            ))}
          </View>
        </View>
      </ScrollView>

      <BlurView intensity={60} tint="light" style={[styles.cta, { paddingBottom: insets.bottom + 12 }]}>
        {isMe ? (
          <Button style={{ flex: 1 }} title={t("edit_profile")} icon="create-outline" onPress={() => router.push("/specialist-form")} testID="edit-own-profile-button" />
        ) : !s.membership_active ? (
          <Text style={[styles.muted, { flex: 1, textAlign: "center", paddingVertical: 14 }]} testID="specialist-unavailable">
            {t("not_available")}
          </Text>
        ) : (
          <>
            <Pressable testID="call-specialist-button" style={styles.iconBtn} onPress={() => Linking.openURL(`tel:${s.phone}`)}>
              <Ionicons name="call" size={20} color={colors.brandPrimary} />
            </Pressable>
            <Pressable testID="whatsapp-specialist-button" style={styles.iconBtn} onPress={() => Linking.openURL(`https://wa.me/${String(s.whatsapp || s.phone).replace(/[^0-9]/g, "")}`)}>
              <Ionicons name="logo-whatsapp" size={20} color={colors.brandPrimary} />
            </Pressable>
            <Pressable testID="chat-specialist-button" style={[styles.iconBtn, { flex: 1, flexDirection: "row", gap: 8 }]} onPress={openChat}>
              <Ionicons name="chatbubble-ellipses" size={20} color={colors.brandPrimary} />
              <Text style={styles.chatText}>{t("chat")}</Text>
            </Pressable>
          </>
        )}
      </BlurView>

      <Modal visible={!!sheet} transparent animationType="slide" onRequestClose={() => setSheet(null)}>
        <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }}>
          <Pressable style={styles.backdrop} onPress={() => setSheet(null)} />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]}>
            <View style={styles.handle} />
            {(
              <>
                <Text style={styles.sheetTitle}>{t("rate_title")}</Text>
                <Text style={styles.label}>{t("rating_once")}</Text>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Pressable key={i} testID={`review-star-${i}`} onPress={() => setRating(i)} hitSlop={6}>
                      <Ionicons name={rating >= i ? "star" : "star-outline"} size={34} color={colors.warning} />
                    </Pressable>
                  ))}
                </View>
                <TextInput testID="review-comment-input" style={[styles.input, { height: 80 }]} multiline maxLength={200} placeholder={t("comment_ph")} placeholderTextColor={colors.muted} value={comment} onChangeText={setComment} textAlignVertical="top" />
                <Button title={t("submit")} onPress={sendReview} loading={busy} disabled={!rating} testID="review-submit-button" />
              </>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <Modal visible={!!preview} transparent animationType="fade" onRequestClose={() => setPreview(null)}>
        <Pressable style={styles.previewBg} onPress={() => setPreview(null)} testID="portfolio-preview">
          {preview && <Image source={{ uri: imageUri(preview) }} style={{ width: "100%", height: "70%" }} contentFit="contain" />}
        </Pressable>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  abs: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  hero: { height: 340, justifyContent: "flex-end" },
  back: { position: "absolute", left: 16, width: 44, height: 44, borderRadius: 22, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center" },
  heroContent: { flexDirection: "row", alignItems: "flex-end", gap: 16, padding: 24 },
  avatarRing: { borderWidth: 3, borderColor: c.onSurfaceInverse, borderRadius: 44 },
  name: { color: c.onSurfaceInverse, fontSize: 26, fontWeight: "800", letterSpacing: -0.5 },
  heroSub: { color: c.onSurfaceInverse, opacity: 0.85, fontSize: 14 },
  stats: { flexDirection: "row", margin: 16, padding: 16, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  stat: { flex: 1, alignItems: "center", gap: 4 },
  statVal: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  statLabel: { fontSize: 11, color: c.muted, fontWeight: "600", textAlign: "center" },
  content: { paddingHorizontal: 16, gap: 32 },
  body: { fontSize: 15, lineHeight: 22, color: c.onSurfaceTertiary },
  muted: { fontSize: 14, color: c.muted },
  infoRow: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  info: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.brandSecondary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999 },
  infoText: { color: c.onBrandSecondary, fontWeight: "600", fontSize: 13 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  gridItem: { width: "48.8%", borderRadius: 12, overflow: "hidden", backgroundColor: c.surfaceTertiary },
  gridImg: { width: "100%", aspectRatio: 1 },
  caption: { fontSize: 12, color: c.onSurfaceTertiary, padding: 8 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  review: { padding: 16, borderRadius: 12, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 8 },
  reviewHead: { flexDirection: "row", alignItems: "center", gap: 12 },
  reviewName: { fontWeight: "700", color: c.onSurface, fontSize: 15, marginBottom: 2 },
  recPill: { backgroundColor: c.brandSecondary, padding: 6, borderRadius: 999 },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", gap: 8, paddingHorizontal: 16, paddingTop: 12, borderTopWidth: 1, borderTopColor: c.border, overflow: "hidden" },
  iconBtn: { width: 50, height: 50, borderRadius: 12, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  chatText: { color: c.brandPrimary, fontWeight: "700", fontSize: 16 },
  backdrop: { flex: 1, backgroundColor: c.scrim },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, gap: 12 },
  handle: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, backgroundColor: c.borderStrong, marginBottom: 4 },
  sheetTitle: { fontSize: 22, fontWeight: "800", color: c.onSurface },
  label: { fontSize: 13, fontWeight: "600", color: c.muted },
  input: { minHeight: 50, borderRadius: 12, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: c.onSurface },
  recRow: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44 },
  previewBg: { flex: 1, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  hiddenBanner: { padding: 16, borderRadius: 16, backgroundColor: c.surfaceTertiary, borderLeftWidth: 4, borderLeftColor: c.warning, gap: 12 },
}));
