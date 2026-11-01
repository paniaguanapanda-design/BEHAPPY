import React, { useMemo, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api, imageSource, uploadRequestPhoto } from "@/src/api";
import { useAuth } from "@/src/auth";
import { ProvincePicker } from "@/src/ProvincePicker";
import { CATEGORIES, useI18n } from "@/src/i18n";
import { queryClient } from "@/src/query-client";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { useMembership } from "@/src/membership";
import { Button } from "@/src/ui";

type PhotoAsset = ImagePicker.ImagePickerAsset;
type Quote = {
  quote_id: string;
  specialist_id: string;
  specialist_name: string;
  price: number;
  currency: string;
  description: string;
  estimated_time: string;
  status: "pending" | "accepted" | "rejected";
  conversation_id?: string;
};
type RequestItem = {
  request_id: string;
  title: string;
  description: string;
  category: string;
  photos: string[];
  city: string;
  status: string;
  created_at: string;
  distance_km?: number;
  quotes?: Quote[];
  quotes_count?: number;
  my_quote?: { quote_id: string; price: number; status: string } | null;
};
type Zone = { province: { code: string; name: string } | null; lat: number | null; lng: number | null };

export default function Requests() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const toast = useToast();
  const isSpecialist = user?.role === "specialist" && !!user.specialist_id;
  const membership = useMembership(isSpecialist);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [changeZone, setChangeZone] = useState(false);
  const zone = useQuery({
    queryKey: ["my-zone"],
    queryFn: () => api<Zone>("/me/zone"),
    enabled: !isSpecialist,
  });
  const specialist = useQuery({
    queryKey: ["specialist-me"],
    queryFn: () => api<{ categories?: string[]; zone?: { label?: string; radius_km?: number } }>("/specialists/me"),
    enabled: isSpecialist,
  });
  const requests = useQuery({
    queryKey: ["marketplace-requests", isSpecialist ? "specialist" : "client"],
    queryFn: () => api<RequestItem[]>("/requests/board"),
    refetchInterval: 30000,
  });

  const categories = isSpecialist ? specialist.data?.categories ?? [] : [...CATEGORIES];
  const filtered = useMemo(
    () => (selectedCategory === "all" ? requests.data ?? [] : (requests.data ?? []).filter((item) => item.category === selectedCategory)),
    [requests.data, selectedCategory],
  );
  const refresh = () => {
    void requests.refetch();
    if (isSpecialist) void specialist.refetch();
    else void zone.refetch();
  };
  const changeQuoteStatus = async (quote: Quote, status: "accepted" | "rejected") => {
    try {
      const result = await api<Quote & { conversation_id?: string }>(`/quotes/${quote.quote_id}`, { method: "PATCH", body: { status } });
      await requests.refetch();
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      if (status === "accepted" && result.conversation_id) {
        router.push({ pathname: "/chat/[id]", params: { id: result.conversation_id } });
      }
    } catch (error: any) {
      toast(error?.message || t("error_generic"), "error");
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={requests.isRefetching} onRefresh={refresh} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}
      >
        <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
          <Text style={styles.title}>{isSpecialist ? t("requests_nearby") : t("my_requests")}</Text>
          <Text style={styles.subtitle}>
            {isSpecialist ? t("requests_pro_sub") : t("requests_client_sub")}
          </Text>
          {isSpecialist ? (
            <View style={styles.zoneCard}>
              <View style={styles.zoneIcon}>
                <Ionicons name="location" size={18} color={colors.onBrandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.zoneTitle}>
                  {specialist.data?.zone?.label || t("turin")} · {specialist.data?.zone?.radius_km ?? 15} km
                </Text>
                <Text style={styles.zoneSub}>{t("requests_matching_sub")}</Text>
              </View>
              <Pressable onPress={() => router.push("/pro-zone")} style={styles.adjust}>
                <Text style={styles.adjustText}>{t("prov_change")}</Text>
              </Pressable>
            </View>
          ) : zone.data?.province ? (
            <View style={styles.clientLocation}>
              <Ionicons name="location" size={15} color={colors.brandPrimary} />
              <Text style={styles.locationText}>
                {t("requests_private_zone")}: {zone.data.province.name}
              </Text>
              <Pressable onPress={() => setChangeZone(!changeZone)} style={styles.adjust}>
                <Text style={styles.adjustText}>{t("prov_change")}</Text>
              </Pressable>
            </View>
          ) : null}
          {!isSpecialist ? (
            <Pressable testID="publish-request-button" onPress={() => setCreateOpen(true)} style={styles.publish}>
              <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
              <Text style={styles.publishText}>{t("requests_publish")}</Text>
            </Pressable>
          ) : null}
        </View>

        {!isSpecialist && changeZone ? (
          <View style={styles.locationPicker}>
            <ProvincePicker onDone={() => { setChangeZone(false); void zone.refetch(); }} onCancel={() => setChangeZone(false)} />
          </View>
        ) : null}
        {!isSpecialist && !zone.isLoading && (!zone.data?.province || zone.data.lat == null || zone.data.lng == null) ? (
          <View style={styles.locationPicker}>
            <ProvincePicker onDone={() => void zone.refetch()} />
          </View>
        ) : null}
        {!isSpecialist && zone.isError ? (
          <Pressable onPress={() => void zone.refetch()} style={styles.errorNotice}>
            <Text style={styles.errorText}>{t("error_generic")}</Text>
            <Text style={styles.adjustText}>{t("retry")}</Text>
          </Pressable>
        ) : null}

        {isSpecialist && membership.data && !membership.data.active ? (
          <View style={styles.membershipNotice}>
            <Ionicons name="lock-closed-outline" size={18} color={colors.onBrandSecondary} />
            <Text style={styles.noticeText}>{t("reply_needs_membership")}</Text>
          </View>
        ) : null}
        {isSpecialist && membership.isError ? (
          <Pressable onPress={() => void membership.refetch()} style={styles.errorNotice}>
            <Text style={styles.errorText}>{t("error_generic")}</Text>
            <Text style={styles.adjustText}>{t("retry")}</Text>
          </Pressable>
        ) : null}

        <View style={styles.sectionHeader}>
          <View>
            <Text style={styles.sectionTitle}>{isSpecialist ? t("requests_open") : t("requests_mine_heading")}</Text>
            <Text style={styles.sectionSubtitle}>
              {isSpecialist
                ? t("requests_count").replace("{n}", String(filtered.length))
                : t("requests_private_contact")}
            </Text>
          </View>
          {!isSpecialist ? <Text style={styles.activeCount}>{requests.data?.filter((item) => item.status === "open").length ?? 0}</Text> : null}
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
          {(isSpecialist ? ["all", ...categories] : ["all", "open", "accepted", "completed", "cancelled"]).map((category) => {
            const active = selectedCategory === category;
            const label = category === "all" ? t("all") : isSpecialist ? t(`cat_${category}`) : t(`request_status_${category}`);
            return (
              <Pressable key={category} onPress={() => setSelectedCategory(category)} style={[styles.filter, active && styles.filterActive]}>
                <Text style={[styles.filterText, active && styles.filterTextActive]}>{label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        {requests.isLoading ? <ActivityIndicator style={{ marginTop: 32 }} color={colors.brandPrimary} /> : null}
        {requests.isError ? (
          <Pressable onPress={() => void requests.refetch()} style={styles.errorNotice}>
            <Text style={styles.errorText}>{t("error_generic")}</Text>
            <Text style={styles.adjustText}>{t("retry")}</Text>
          </Pressable>
        ) : null}
        {!requests.isLoading && !requests.isError && !filtered.length ? (
          <View style={styles.empty}>
            <Ionicons name={isSpecialist ? "briefcase-outline" : "document-text-outline"} size={42} color={colors.brandTertiary} />
            <Text style={styles.emptyTitle}>{isSpecialist ? t("requests_no_opportunities") : t("requests_no_posts")}</Text>
            <Text style={styles.emptyText}>{isSpecialist ? t("requests_no_opportunities_sub") : t("requests_no_posts_sub")}</Text>
          </View>
        ) : null}

        <View style={styles.list}>
          {filtered.map((item) => (
            <View key={item.request_id} style={styles.card}>
              <View style={styles.cardTop}>
                <View style={styles.categoryChip}>
                  <Ionicons name="construct-outline" size={14} color={colors.onBrandSecondary} />
                  <Text style={styles.categoryText}>{t(`cat_${item.category}`)}</Text>
                </View>
                <Text style={styles.cardTime}>{relativeTime(item.created_at, t)}</Text>
              </View>
              <Text style={styles.cardTitle}>{item.title}</Text>
              <Text style={styles.cardDescription}>{item.description}</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.photos}>
                {item.photos.map((path) => {
                  const source = imageSource(path);
                  return source ? <Image key={path} source={source} style={styles.photo} contentFit="cover" /> : null;
                })}
              </ScrollView>

              {isSpecialist ? (
                <>
                  <View style={styles.privacyLine}>
                    <Ionicons name="location-outline" size={14} color={colors.brandTertiary} />
                    <Text style={styles.privacyText}>
                      {item.city}{item.distance_km != null ? ` · ${t("requests_approx_distance").replace("{n}", String(item.distance_km))}` : ""}
                    </Text>
                    <Ionicons name="shield-checkmark-outline" size={14} color={colors.success} />
                    <Text style={styles.privacyText}>{t("requests_contact_private")}</Text>
                  </View>
                  {item.my_quote ? (
                    <View style={styles.myQuote}>
                      <Text style={styles.myQuoteText}>
                        {t("requests_quote_sent")}: {formatPrice(item.my_quote.price, lang)} · {t(`qs_${item.my_quote.status}`)}
                      </Text>
                    </View>
                  ) : membership.data?.active ? (
                    <SpecialistQuoteForm request={item} onSent={() => void requests.refetch()} />
                  ) : null}
                </>
              ) : (
                <>
                  <View style={styles.clientStatus}>
                    <Text style={styles.statusText}>{t(`request_status_${item.status}`)}</Text>
                    <Text style={styles.quoteCount}>
                      {(item.quotes?.length ?? 0)} {t("quotes").toLowerCase()}
                    </Text>
                  </View>
                  {(item.quotes ?? []).map((quote) => (
                    <View key={quote.quote_id} style={styles.offerCard}>
                      <View style={styles.offerHeading}>
                        <Text style={styles.offerName}>{quote.specialist_name}</Text>
                        <Text style={styles.offerPrice}>{formatPrice(quote.price, lang)}</Text>
                      </View>
                      <Text style={styles.offerDescription}>{quote.description}</Text>
                      {quote.estimated_time ? <Text style={styles.offerTime}>{t("quote_time")}: {quote.estimated_time}</Text> : null}
                      {quote.status === "pending" && item.status === "open" ? (
                        <View style={styles.offerActions}>
                          <Pressable onPress={() => void changeQuoteStatus(quote, "rejected")} style={styles.rejectButton}>
                            <Text style={styles.rejectText}>{t("reject")}</Text>
                          </Pressable>
                          <Pressable onPress={() => void changeQuoteStatus(quote, "accepted")} style={styles.acceptButton}>
                            <Text style={styles.acceptText}>{t("accept")}</Text>
                          </Pressable>
                        </View>
                      ) : quote.status === "accepted" && quote.conversation_id ? (
                        <Button title={t("open_chat")} icon="chatbubble-outline" onPress={() => router.push({ pathname: "/chat/[id]", params: { id: quote.conversation_id! } })} />
                      ) : (
                        <Text style={styles.offerStatus}>{t(`qs_${quote.status}`)}</Text>
                      )}
                    </View>
                  ))}
                  {item.status === "open" ? (
                    <Pressable
                      onPress={async () => {
                        try {
                          await api(`/requests/${item.request_id}`, { method: "PATCH", body: { status: "cancelled" } });
                          await requests.refetch();
                        } catch (error: any) {
                          toast(error?.message || t("error_generic"), "error");
                        }
                      }}
                      style={styles.cancelRequest}
                    >
                      <Text style={styles.cancelText}>{t("requests_close")}</Text>
                    </Pressable>
                  ) : null}
                </>
              )}
            </View>
          ))}
        </View>
      </ScrollView>

      <CreateRequestModal visible={createOpen} zone={zone.data} onClose={() => setCreateOpen(false)} onCreated={() => {
        setCreateOpen(false);
        setSelectedCategory("all");
        void requests.refetch();
      }} />
    </View>
  );
}

function SpecialistQuoteForm({ request, onSent }: { request: RequestItem; onSent: () => void }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState("");
  const [description, setDescription] = useState("");
  const [time, setTime] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async () => {
    const amount = Number(price.replace(",", "."));
    if (!Number.isFinite(amount) || amount <= 0 || !description.trim()) return toast(t("required"), "error");
    setBusy(true);
    try {
      await api(`/requests/board/${request.request_id}/quotes`, {
        body: { price: amount, description: description.trim(), estimated_time: time.trim() },
      });
      toast(t("quote_sent"));
      setOpen(false);
      onSent();
    } catch (error: any) {
      toast(error?.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };
  return open ? (
    <View style={styles.quoteForm}>
      <Text style={styles.formTitle}>{t("send_quote")}</Text>
      <TextInput testID={`quote-price-${request.request_id}`} value={price} onChangeText={setPrice} placeholder={t("quote_price")} placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={styles.input} />
      <TextInput testID={`quote-description-${request.request_id}`} value={description} onChangeText={setDescription} placeholder={t("quote_desc")} placeholderTextColor={colors.muted} multiline maxLength={1000} style={[styles.input, styles.multiline]} />
      <TextInput value={time} onChangeText={setTime} placeholder={t("quote_time")} placeholderTextColor={colors.muted} style={styles.input} />
      <View style={styles.formActions}>
        <Pressable onPress={() => setOpen(false)} style={styles.rejectButton}><Text style={styles.rejectText}>{t("cancel")}</Text></Pressable>
        <Pressable disabled={busy} onPress={() => void send()} style={styles.acceptButton}>
          {busy ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.acceptText}>{t("send_quote")}</Text>}
        </Pressable>
      </View>
    </View>
  ) : (
    <Pressable testID={`send-quote-${request.request_id}`} onPress={() => setOpen(true)} style={styles.sendQuote}>
      <Ionicons name="paper-plane-outline" size={16} color={colors.onBrandPrimary} />
      <Text style={styles.sendQuoteText}>{t("send_quote")}</Text>
    </Pressable>
  );
}

function CreateRequestModal({ visible, zone, onClose, onCreated }: {
  visible: boolean;
  zone?: Zone;
  onClose: () => void;
  onCreated: () => void;
}) {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { t } = useI18n();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<string>(CATEGORIES[0]);
  const [photos, setPhotos] = useState<PhotoAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const canPublish = !!zone?.province && zone.lat != null && zone.lng != null;

  const close = () => {
    if (busy) return;
    setTitle("");
    setDescription("");
    setPhotos([]);
    onClose();
  };
  const choosePhotos = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsMultipleSelection: true,
        selectionLimit: 4 - photos.length,
        quality: 0.85,
      });
      if (!result.canceled) setPhotos((current) => [...current, ...result.assets].slice(0, 4));
    } catch (error: any) {
      toast(error?.message || t("error_generic"), "error");
    }
  };
  const publish = async () => {
    if (!title.trim() || !description.trim() || !canPublish) return toast(t("required"), "error");
    setBusy(true);
    try {
      const paths: string[] = [];
      for (const photo of photos) {
        const image = ImageManipulator.manipulate(photo.uri);
        if (photo.width >= photo.height && photo.width > 1600) image.resize({ width: 1600 });
        else if (photo.height > 1600) image.resize({ height: 1600 });
        const jpeg = await (await image.renderAsync()).saveAsync({ format: SaveFormat.JPEG, compress: 0.82 });
        paths.push(await uploadRequestPhoto(jpeg.uri, "image/jpeg"));
      }
      await api("/requests/board", { body: { title: title.trim(), description: description.trim(), category, photos: paths } });
      queryClient.invalidateQueries({ queryKey: ["marketplace-requests"] });
      toast(t("requests_published"));
      setTitle("");
      setDescription("");
      setPhotos([]);
      onCreated();
    } catch (error: any) {
      toast(error?.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={close}>
      <KeyboardAvoidingView style={styles.modalRoot} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={[styles.modalHeader, { paddingTop: insets.top + 8 }]}>
          <Pressable onPress={close} style={styles.modalBack}><Ionicons name="close" size={23} color={colors.onSurface} /></Pressable>
          <Text style={styles.modalTitle}>{t("requests_new_title")}</Text>
          <View style={{ width: 42 }} />
        </View>
        <ScrollView contentContainerStyle={[styles.modalBody, { paddingBottom: insets.bottom + 28 }]} keyboardShouldPersistTaps="handled">
          <View style={styles.privacyNotice}>
            <Ionicons name="shield-checkmark-outline" size={18} color={colors.brandTertiary} />
            <Text style={styles.privacyNoticeText}>{t("requests_privacy_notice")}</Text>
          </View>
          <Text style={styles.fieldLabel}>{t("requests_work_title")}</Text>
          <TextInput testID="request-title-input" value={title} onChangeText={setTitle} maxLength={120} placeholder={t("requests_title_placeholder")} placeholderTextColor={colors.muted} style={styles.input} />
          <Text style={styles.fieldLabel}>{t("category")}</Text>
          <View style={styles.categoryOptions}>
            {CATEGORIES.map((item) => {
              const active = category === item;
              return (
                <Pressable key={item} onPress={() => setCategory(item)} style={[styles.categoryOption, active && styles.categoryOptionOn]}>
                  <Text style={[styles.categoryOptionText, active && styles.categoryOptionTextOn]}>{t(`cat_${item}`)}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.fieldLabel}>{t("requests_description")}</Text>
          <TextInput testID="request-description-input" value={description} onChangeText={setDescription} multiline maxLength={2000} placeholder={t("requests_description_placeholder")} placeholderTextColor={colors.muted} textAlignVertical="top" style={[styles.input, styles.descriptionInput]} />
          <View style={styles.photoLabelRow}>
            <Text style={styles.fieldLabel}>{t("requests_photos")}</Text>
            <Text style={styles.photoLimit}>{photos.length}/4</Text>
          </View>
          <View style={styles.photoPickerRow}>
            {photos.map((photo, index) => (
              <View key={`${photo.uri}-${index}`} style={styles.selectedPhoto}>
                <Image source={{ uri: photo.uri }} style={styles.selectedPhotoImage} />
                <Pressable onPress={() => setPhotos((current) => current.filter((_, i) => i !== index))} style={styles.removePhoto}>
                  <Ionicons name="close" size={14} color={colors.onSurfaceInverse} />
                </Pressable>
              </View>
            ))}
            {photos.length < 4 ? (
              <Pressable testID="request-add-photo" onPress={() => void choosePhotos()} style={styles.addPhoto}>
                <Ionicons name="camera-outline" size={22} color={colors.brandTertiary} />
                <Text style={styles.addPhotoText}>{t("add_photo")}</Text>
              </Pressable>
            ) : null}
          </View>
          <View style={styles.locationNotice}>
            <Ionicons name="location" size={16} color={colors.brandPrimary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.locationTitle}>{t("requests_location_label")}</Text>
              <Text style={styles.locationSub}>{zone?.province?.name ?? t("requests_location_missing")}</Text>
            </View>
            <Text style={styles.approximate}>{t("requests_approx_only")}</Text>
          </View>
          <Text style={styles.privacyFootnote}>{t("requests_no_contact_shared")}</Text>
          <Button testID="request-publish-submit" title={t("requests_publish")} icon="paper-plane-outline" loading={busy} disabled={!canPublish || !title.trim() || !description.trim()} onPress={() => void publish()} />
        </ScrollView>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function relativeTime(value: string, t: (key: string) => string) {
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) return t("time_now");
  if (minutes < 60) return t("time_minutes_ago").replace("{n}", String(minutes));
  const hours = Math.floor(minutes / 60);
  return hours < 24
    ? t("time_hours_ago").replace("{n}", String(hours))
    : t("time_days_ago").replace("{n}", String(Math.floor(hours / 24)));
}

function formatPrice(value: number, lang: string) {
  return new Intl.NumberFormat(lang === "it" ? "it-IT" : "es-ES", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 20, paddingBottom: 18 },
  title: { color: c.onSurface, fontFamily: fonts.display, fontSize: 28, letterSpacing: -0.5 },
  subtitle: { marginTop: 4, color: c.muted, fontSize: 13, lineHeight: 18 },
  zoneCard: { marginTop: 16, padding: 11, backgroundColor: c.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: c.border, flexDirection: "row", alignItems: "center", gap: 9 },
  zoneIcon: { width: 34, height: 34, borderRadius: 11, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  zoneTitle: { color: c.onSurface, fontSize: 12, fontWeight: "800" },
  zoneSub: { marginTop: 3, color: c.muted, fontSize: 10 },
  adjust: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: 8, backgroundColor: c.surfaceTertiary },
  adjustText: { color: c.brandTertiary, fontSize: 11, fontWeight: "700" },
  clientLocation: { marginTop: 13, flexDirection: "row", alignItems: "center", gap: 6 },
  locationText: { flex: 1, color: c.onSurfaceTertiary, fontSize: 12, fontWeight: "600" },
  publish: { marginTop: 16, height: 48, borderRadius: 13, backgroundColor: c.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 },
  publishText: { color: c.onBrandPrimary, fontSize: 14, fontWeight: "800" },
  locationPicker: { paddingHorizontal: 16, paddingBottom: 14 },
  membershipNotice: { marginHorizontal: 16, marginBottom: 12, padding: 14, borderRadius: 14, backgroundColor: c.brandSecondary, gap: 8 },
  noticeText: { color: c.onBrandSecondary, fontSize: 13, lineHeight: 18 },
  errorNotice: { marginHorizontal: 16, marginVertical: 8, padding: 12, borderRadius: 10, backgroundColor: c.surfaceTertiary, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  errorText: { color: c.error, fontSize: 11, fontWeight: "700" },
  sectionHeader: { paddingHorizontal: 20, marginTop: 8, marginBottom: 12, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  sectionTitle: { color: c.onSurface, fontSize: 18, fontWeight: "800" },
  sectionSubtitle: { marginTop: 3, color: c.muted, fontSize: 10 },
  activeCount: { minWidth: 27, height: 27, borderRadius: 14, textAlign: "center", lineHeight: 27, overflow: "hidden", backgroundColor: c.brandSecondary, color: c.onBrandSecondary, fontSize: 12, fontWeight: "800" },
  filters: { paddingHorizontal: 16, gap: 8, paddingBottom: 12 },
  filter: { paddingHorizontal: 13, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary },
  filterActive: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  filterText: { color: c.onSurfaceTertiary, fontSize: 11, fontWeight: "600" },
  filterTextActive: { color: c.onSurfaceInverse },
  empty: { alignItems: "center", paddingHorizontal: 36, paddingVertical: 34, gap: 8 },
  emptyTitle: { color: c.onSurface, fontSize: 16, fontWeight: "800", textAlign: "center" },
  emptyText: { color: c.muted, fontSize: 12, lineHeight: 18, textAlign: "center" },
  list: { paddingHorizontal: 15, gap: 12 },
  card: { padding: 14, borderRadius: 17, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  cardTop: { flexDirection: "row", alignItems: "center", gap: 8 },
  categoryChip: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, backgroundColor: c.brandSecondary },
  categoryText: { color: c.onBrandSecondary, fontSize: 10, fontWeight: "700" },
  cardTime: { flex: 1, color: c.muted, fontSize: 10 },
  cardTitle: { marginTop: 10, color: c.onSurface, fontFamily: fonts.display, fontSize: 18 },
  cardDescription: { marginTop: 3, color: c.onSurfaceTertiary, fontSize: 12, lineHeight: 17 },
  photos: { gap: 8, marginTop: 10 },
  photo: { width: 122, height: 92, borderRadius: 10, backgroundColor: c.surfaceTertiary },
  privacyLine: { marginTop: 10, flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 5 },
  privacyText: { color: c.onSurfaceTertiary, fontSize: 10 },
  myQuote: { marginTop: 10, padding: 10, borderRadius: 9, backgroundColor: c.surfaceTertiary },
  myQuoteText: { color: c.onSurfaceTertiary, fontSize: 11, fontWeight: "700" },
  sendQuote: { marginTop: 12, height: 42, borderRadius: 10, backgroundColor: c.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 },
  sendQuoteText: { color: c.onBrandPrimary, fontSize: 12, fontWeight: "800" },
  quoteForm: { marginTop: 12, padding: 12, borderRadius: 12, backgroundColor: c.surface, gap: 9 },
  formTitle: { color: c.onSurface, fontSize: 14, fontWeight: "800" },
  input: { minHeight: 46, paddingHorizontal: 12, borderRadius: 10, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, color: c.onSurface, fontSize: 14 },
  multiline: { minHeight: 78, paddingTop: 11, textAlignVertical: "top" },
  formActions: { flexDirection: "row", justifyContent: "flex-end", gap: 8 },
  rejectButton: { minHeight: 38, justifyContent: "center", paddingHorizontal: 12, borderRadius: 9, backgroundColor: c.surfaceTertiary },
  rejectText: { color: c.onSurfaceTertiary, fontSize: 12, fontWeight: "700" },
  acceptButton: { minHeight: 38, minWidth: 96, alignItems: "center", justifyContent: "center", paddingHorizontal: 12, borderRadius: 9, backgroundColor: c.brandPrimary },
  acceptText: { color: c.onBrandPrimary, fontSize: 12, fontWeight: "800" },
  clientStatus: { marginTop: 10, paddingTop: 9, borderTopWidth: 1, borderTopColor: c.divider, flexDirection: "row", justifyContent: "space-between" },
  statusText: { color: c.onSurfaceTertiary, fontSize: 11, fontWeight: "700" },
  quoteCount: { color: c.muted, fontSize: 10 },
  offerCard: { marginTop: 9, padding: 11, borderRadius: 12, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface },
  offerHeading: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  offerName: { flex: 1, color: c.onSurface, fontSize: 13, fontWeight: "800" },
  offerPrice: { color: c.brandTertiary, fontSize: 14, fontWeight: "800" },
  offerDescription: { marginTop: 5, color: c.onSurfaceTertiary, fontSize: 11, lineHeight: 16 },
  offerTime: { marginTop: 5, color: c.muted, fontSize: 10 },
  offerActions: { marginTop: 10, flexDirection: "row", justifyContent: "flex-end", gap: 8 },
  offerStatus: { marginTop: 8, color: c.onSurfaceTertiary, fontSize: 11, fontWeight: "700" },
  cancelRequest: { alignSelf: "flex-end", marginTop: 10, padding: 5 },
  cancelText: { color: c.error, fontSize: 11, fontWeight: "700" },
  modalRoot: { flex: 1, backgroundColor: c.surface },
  modalHeader: { minHeight: 58, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderBottomColor: c.border },
  modalBack: { width: 42, height: 42, alignItems: "center", justifyContent: "center" },
  modalTitle: { color: c.onSurface, fontFamily: fonts.display, fontSize: 19 },
  modalBody: { padding: 18, gap: 10 },
  privacyNotice: { marginBottom: 7, padding: 12, borderRadius: 12, backgroundColor: c.brandSecondary, flexDirection: "row", alignItems: "flex-start", gap: 8 },
  privacyNoticeText: { flex: 1, color: c.onBrandSecondary, fontSize: 11, lineHeight: 16 },
  fieldLabel: { marginTop: 5, color: c.onSurface, fontSize: 13, fontWeight: "800" },
  categoryOptions: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  categoryOption: { paddingHorizontal: 11, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary },
  categoryOptionOn: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  categoryOptionText: { color: c.onSurfaceTertiary, fontSize: 11, fontWeight: "600" },
  categoryOptionTextOn: { color: c.onSurfaceInverse },
  descriptionInput: { minHeight: 104, paddingTop: 12, textAlignVertical: "top" },
  photoLabelRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  photoLimit: { color: c.muted, fontSize: 11 },
  photoPickerRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  selectedPhoto: { width: 78, height: 72, borderRadius: 10, overflow: "hidden" },
  selectedPhotoImage: { width: "100%", height: "100%" },
  removePhoto: { position: "absolute", right: 4, top: 4, width: 22, height: 22, borderRadius: 11, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center" },
  addPhoto: { width: 92, height: 72, borderRadius: 10, borderWidth: 1, borderColor: c.borderStrong, borderStyle: "dashed", alignItems: "center", justifyContent: "center", gap: 2, backgroundColor: c.surfaceSecondary },
  addPhotoText: { color: c.brandTertiary, fontSize: 10, fontWeight: "700" },
  locationNotice: { marginTop: 8, padding: 11, borderRadius: 11, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, flexDirection: "row", alignItems: "center", gap: 8 },
  locationTitle: { color: c.onSurface, fontSize: 11, fontWeight: "800" },
  locationSub: { marginTop: 2, color: c.muted, fontSize: 10 },
  approximate: { color: c.brandTertiary, fontSize: 9, fontWeight: "700" },
  privacyFootnote: { marginVertical: 3, color: c.muted, fontSize: 10, lineHeight: 14, textAlign: "center" },
}));
