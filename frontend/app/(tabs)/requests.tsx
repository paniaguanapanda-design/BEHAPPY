import React, { useMemo, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api, imageSource } from "@/src/api";
import { useAuth } from "@/src/auth";
import { ProvincePicker } from "@/src/ProvincePicker";
import { CATEGORIES, useI18n } from "@/src/i18n";
import { queryClient } from "@/src/query-client";
import { useToast } from "@/src/toast";
import { useTheme } from "@/src/theme";
import { useMembership } from "@/src/membership";
import { Button } from "@/src/ui";
import { CreateRequestModal } from "@/src/requests/CreateRequestModal";
import { SpecialistQuoteForm } from "@/src/requests/SpecialistQuoteForm";
import { formatPrice, relativeTime } from "@/src/requests/format";
import { useRequestStyles } from "@/src/requests/styles";
import type { Quote, RequestItem, Zone } from "@/src/requests/types";

export default function Requests() {
  const styles = useRequestStyles();
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
