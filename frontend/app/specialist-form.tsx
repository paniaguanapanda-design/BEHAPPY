import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api, imageUri, uploadImage } from "@/src/api";
import { useAuth } from "@/src/auth";
import { CATEGORIES, useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme } from "@/src/theme";
import { Avatar, Button, SectionTitle, VerifiedBadge } from "@/src/ui";

async function pick(): Promise<ImagePicker.ImagePickerAsset | null> {
  const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.6 });
  return r.canceled ? null : r.assets[0];
}

export default function SpecialistForm() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const me = useQuery({ queryKey: ["specialist-me"], queryFn: () => api<any>("/specialists/me"), enabled: !!user?.specialist_id, retry: false });

  const [f, setF] = useState({ name: user?.name || "", category: "plumbing", bio: "", phone: "", whatsapp: "", city: "", years_experience: "", hourly_rate: "", avatar: user?.picture || "" });
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [caption, setCaption] = useState("");
  const [docNum, setDocNum] = useState("");
  const [docImg, setDocImg] = useState<string | null>(null);

  useEffect(() => {
    const s = me.data;
    if (s)
      setF({
        name: s.name, category: s.category, bio: s.bio || "", phone: s.phone || "", whatsapp: s.whatsapp || "", city: s.city || "",
        years_experience: String(s.years_experience ?? ""), hourly_rate: s.hourly_rate || "", avatar: s.avatar || "",
      });
  }, [me.data]);

  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));

  const upload = async (key: string): Promise<string | null> => {
    const a = await pick();
    if (!a) return null;
    setUploading(key);
    try {
      return await uploadImage(a.uri, a.mimeType);
    } catch (e: any) {
      toast(e.message, "error");
      return null;
    } finally {
      setUploading(null);
    }
  };

  const save = async () => {
    if (!f.name.trim() || !f.phone.trim()) return toast(t("required"), "error");
    setSaving(true);
    try {
      await api("/specialists", { body: { ...f, years_experience: parseInt(f.years_experience || "0", 10) || 0 } });
      await refreshUser();
      await me.refetch();
      queryClient.invalidateQueries({ queryKey: ["specialists"] });
      toast(t("saved"));
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const addWork = async () => {
    const path = await upload("work");
    if (!path) return;
    try {
      await api("/specialists/me/portfolio", { body: { image: path, caption } });
      setCaption("");
      me.refetch();
      toast(t("saved"));
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const removeWork = async (itemId: string) => {
    await api(`/specialists/me/portfolio/${itemId}`, { method: "DELETE" });
    me.refetch();
  };

  const verify = async () => {
    if (!docImg || docNum.trim().length < 5) return toast(t("required"), "error");
    try {
      await api("/specialists/me/verify", { body: { document_image: docImg, document_number: docNum } });
      me.refetch();
      toast(t("verified_ok"));
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const s = me.data;
  const field = (k: keyof typeof f, ph: string, extra: object = {}) => (
    <TextInput testID={`specialist-${k}-input`} style={styles.input} placeholder={ph} placeholderTextColor={colors.muted} value={f[k]} onChangeText={set(k)} {...extra} />
  );

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="form-back-button" onPress={() => router.back()} style={styles.back}>
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("form_title")}</Text>
      </View>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: insets.bottom + 32 }} keyboardShouldPersistTaps="handled">
        <View style={styles.avatarRow}>
          <Avatar uri={f.avatar} name={f.name} size={80} />
          <Button
            variant="secondary"
            icon="camera-outline"
            title={t("change_photo")}
            loading={uploading === "avatar"}
            onPress={async () => {
              const p = await upload("avatar");
              if (p) set("avatar")(p);
            }}
            testID="change-avatar-button"
          />
        </View>
        {field("name", t("name"))}
        <Text style={styles.label}>{t("category")}</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ flexGrow: 0 }}>
          {CATEGORIES.map((c) => (
            <Pressable key={c} testID={`form-category-${c}`} onPress={() => set("category")(c)} style={[styles.chip, f.category === c && styles.chipOn]}>
              <Text style={[styles.chipText, f.category === c && styles.chipTextOn]}>{t(`cat_${c}`)}</Text>
            </Pressable>
          ))}
        </ScrollView>
        {field("bio", t("bio"), { multiline: true, style: [styles.input, { height: 100, textAlignVertical: "top" }] })}
        {field("phone", t("phone") + " *", { keyboardType: "phone-pad" })}
        {field("whatsapp", t("whatsapp"), { keyboardType: "phone-pad" })}
        {field("city", t("city"))}
        <View style={{ flexDirection: "row", gap: 12 }}>
          <View style={{ flex: 1 }}>{field("years_experience", t("years_exp"), { keyboardType: "number-pad" })}</View>
          <View style={{ flex: 1 }}>{field("hourly_rate", t("rate"))}</View>
        </View>
        <Button title={t("save")} onPress={save} loading={saving} testID="specialist-save-button" />

        {!s ? (
          <Text style={styles.hint}>{t("save_first")}</Text>
        ) : (
          <>
            <View style={{ marginTop: 24, gap: 12 }}>
              <SectionTitle>{t("portfolio")}</SectionTitle>
              <TextInput testID="portfolio-caption-input" style={styles.input} placeholder={t("caption")} placeholderTextColor={colors.muted} value={caption} onChangeText={setCaption} />
              <Button variant="secondary" icon="add" title={t("add_work")} loading={uploading === "work"} onPress={addWork} testID="add-portfolio-button" />
              <View style={styles.grid}>
                {s.portfolio?.map((p: any) => (
                  <View key={p.item_id} style={styles.gridItem}>
                    <Image source={{ uri: imageUri(p.image) }} style={styles.gridImg} contentFit="cover" />
                    <Pressable testID={`delete-portfolio-${p.item_id}`} onPress={() => removeWork(p.item_id)} style={styles.del}>
                      <Ionicons name="trash" size={16} color={colors.onError} />
                    </Pressable>
                  </View>
                ))}
              </View>
            </View>

            <View style={styles.verifyBox}>
              <SectionTitle>{t("verification")}</SectionTitle>
              {s.verified ? (
                <View testID="verification-status-verified">
                  <VerifiedBadge label={t("verified_ok")} />
                </View>
              ) : (
                <>
                  <Text style={styles.hint}>{t("verify_text")}</Text>
                  <TextInput testID="verify-doc-number-input" style={styles.input} placeholder={t("doc_number")} placeholderTextColor={colors.muted} value={docNum} onChangeText={setDocNum} />
                  <Pressable
                    testID="verify-doc-photo-button"
                    style={styles.docPick}
                    onPress={async () => {
                      const p = await upload("doc");
                      if (p) setDocImg(p);
                    }}
                  >
                    {uploading === "doc" ? (
                      <ActivityIndicator color={colors.brandPrimary} />
                    ) : docImg ? (
                      <Image source={{ uri: imageUri(docImg) }} style={{ width: "100%", height: "100%" }} contentFit="cover" />
                    ) : (
                      <>
                        <Ionicons name="id-card-outline" size={28} color={colors.brandPrimary} />
                        <Text style={styles.docText}>{t("doc_photo")}</Text>
                      </>
                    )}
                  </Pressable>
                  <Button title={t("verify_btn")} icon="shield-checkmark" onPress={verify} testID="verify-submit-button" />
                </>
              )}
            </View>
          </>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: c.divider },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  avatarRow: { flexDirection: "row", alignItems: "center", gap: 16, marginBottom: 8 },
  label: { fontSize: 13, fontWeight: "600", color: c.muted, marginTop: 4 },
  input: { minHeight: 50, borderRadius: 12, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: c.onSurface },
  chip: { height: 36, flexShrink: 0, paddingHorizontal: 14, borderRadius: 999, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, justifyContent: "center" },
  chipOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontSize: 14, fontWeight: "600", color: c.onSurfaceTertiary },
  chipTextOn: { color: c.onBrandPrimary },
  hint: { fontSize: 14, color: c.muted, lineHeight: 20 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  gridItem: { width: "31.8%", aspectRatio: 1, borderRadius: 10, overflow: "hidden" },
  gridImg: { width: "100%", height: "100%" },
  del: { position: "absolute", top: 6, right: 6, width: 30, height: 30, borderRadius: 15, backgroundColor: c.error, alignItems: "center", justifyContent: "center" },
  verifyBox: { marginTop: 24, gap: 12, padding: 16, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  docPick: { height: 140, borderRadius: 12, borderWidth: 1.5, borderStyle: "dashed", borderColor: c.borderStrong, alignItems: "center", justifyContent: "center", gap: 6, overflow: "hidden" },
  docText: { color: c.brandPrimary, fontWeight: "600" },
}));
