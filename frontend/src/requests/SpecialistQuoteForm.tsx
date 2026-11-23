import React, { useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { useTheme } from "@/src/theme";
import { useRequestStyles } from "./styles";
import type { RequestItem } from "./types";

/** Boton "Enviar presupuesto" que se abre en un formulario (precio, descripcion y tiempo estimado). */
export function SpecialistQuoteForm({ request, onSent }: { request: RequestItem; onSent: () => void }) {
  const styles = useRequestStyles();
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
