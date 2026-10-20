import React, { useState } from "react";
import { Modal, Pressable, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useRouter } from "expo-router";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme } from "@/src/theme";
import { Button } from "@/src/ui";

export type Quote = {
  quote_id: string;
  request_id: string;
  price: number;
  currency: string;
  description: string;
  estimated_time?: string;
  status: "pending" | "accepted" | "rejected";
  client_id: string;
};

const refresh = () => {
  queryClient.invalidateQueries({ queryKey: ["requests"] });
  queryClient.invalidateQueries({ queryKey: ["messages"] });
};

export function QuoteModal({ requestId, onClose }: { requestId: string | null; onClose: () => void }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t } = useI18n();
  const toast = useToast();
  const [price, setPrice] = useState("");
  const [desc, setDesc] = useState("");
  const [time, setTime] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const p = parseFloat(price.replace(",", "."));
    if (!p || p <= 0 || !desc.trim()) return toast(t("required"), "error");
    setBusy(true);
    try {
      await api(`/requests/${requestId}/quotes`, { body: { price: p, description: desc, estimated_time: time } });
      toast(t("quote_sent"));
      setPrice("");
      setDesc("");
      setTime("");
      refresh();
      onClose();
    } catch (e: any) {
      if (String(e.message).includes("membership")) {
        onClose();
        router.push("/membership");
      }
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={!!requestId} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]}>
          <View style={styles.handle} />
          <Text style={styles.title}>{t("send_quote")}</Text>
          <TextInput testID="quote-price-input" style={styles.input} placeholder={t("quote_price")} placeholderTextColor={colors.muted} keyboardType="decimal-pad" value={price} onChangeText={setPrice} />
          <TextInput testID="quote-description-input" style={[styles.input, { height: 90 }]} multiline textAlignVertical="top" placeholder={t("quote_desc")} placeholderTextColor={colors.muted} value={desc} onChangeText={setDesc} />
          <TextInput testID="quote-time-input" style={styles.input} placeholder={t("quote_time")} placeholderTextColor={colors.muted} value={time} onChangeText={setTime} />
          <Button title={t("submit")} icon="send" onPress={submit} loading={busy} testID="quote-submit-button" />
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

export function QuoteCard({ quote, canAnswer }: { quote: Quote; canAnswer: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const color = quote.status === "accepted" ? colors.success : quote.status === "rejected" ? colors.error : colors.warning;

  const answer = async (status: "accepted" | "rejected") => {
    setBusy(status);
    try {
      await api(`/quotes/${quote.quote_id}`, { method: "PATCH", body: { status } });
      toast(t(status === "accepted" ? "quote_accepted" : "quote_rejected"));
      refresh();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={styles.card} testID={`quote-card-${quote.quote_id}`}>
      <View style={styles.cardHead}>
        <Ionicons name="pricetag" size={16} color={colors.brandPrimary} />
        <Text style={styles.cardTitle}>{t("quote")}</Text>
        <View style={[styles.pill, { backgroundColor: color }]}>
          <Text style={styles.pillText} testID={`quote-status-${quote.quote_id}`}>
            {t(`qs_${quote.status}`)}
          </Text>
        </View>
      </View>
      <Text style={styles.price}>{quote.price.toFixed(2).replace(".", ",")} €</Text>
      <Text style={styles.desc}>{quote.description}</Text>
      {quote.estimated_time ? (
        <View style={styles.timeRow}>
          <Ionicons name="time-outline" size={14} color={colors.muted} />
          <Text style={styles.time}>{quote.estimated_time}</Text>
        </View>
      ) : null}
      {canAnswer && quote.status === "pending" && (
        <View style={styles.actions}>
          <Button style={{ flex: 1, minHeight: 42 }} variant="danger" title={t("reject")} loading={busy === "rejected"} onPress={() => answer("rejected")} testID={`quote-reject-${quote.quote_id}`} />
          <Button style={{ flex: 1, minHeight: 42 }} title={t("accept")} loading={busy === "accepted"} onPress={() => answer("accepted")} testID={`quote-accept-${quote.quote_id}`} />
        </View>
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  backdrop: { flex: 1, backgroundColor: c.scrim },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, gap: 12 },
  handle: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, backgroundColor: c.borderStrong, marginBottom: 4 },
  title: { fontSize: 22, fontWeight: "800", color: c.onSurface },
  input: { minHeight: 50, borderRadius: 12, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: c.onSurface },
  card: { padding: 14, borderRadius: 14, backgroundColor: c.surfaceSecondary, borderWidth: 1.5, borderColor: c.brandTertiary, gap: 6 },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  cardTitle: { flex: 1, fontWeight: "800", color: c.onSurface, fontSize: 14 },
  pill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  pillText: { color: c.onSuccess, fontSize: 11, fontWeight: "700" },
  price: { fontSize: 24, fontWeight: "800", color: c.brandPrimary, letterSpacing: -0.5 },
  desc: { fontSize: 14, color: c.onSurfaceTertiary, lineHeight: 20 },
  timeRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  time: { fontSize: 13, color: c.muted },
  actions: { flexDirection: "row", gap: 8, marginTop: 6 },
}));
