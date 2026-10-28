import React, { useState } from "react";
import { ActivityIndicator, Alert, Modal, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme, fonts } from "@/src/theme";

type Props = {
  visible: boolean;
  onClose: () => void;
  targetType: string;
  targetId: string;
  blockUserId?: string;
  onBlocked?: () => void;
};

const REASONS = [
  { key: "inappropriate", es: "Contenido inapropiado u ofensivo", it: "Contenuto inappropriato o offensivo" },
  { key: "harassment", es: "Acoso o amenazas", it: "Molestie o minacce" },
  { key: "fraud", es: "Estafa o engaño", it: "Truffa o inganno" },
  { key: "spam", es: "Spam o publicidad", it: "Spam o pubblicità" },
  { key: "other", es: "Otro motivo", it: "Altro motivo" },
];

export function ReportSheet({ visible, onClose, targetType, targetId, blockUserId, onBlocked }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { lang } = useI18n();
  const toast = useToast();
  const it = lang === "it";
  const [busy, setBusy] = useState(false);

  const sendReport = async (reason: string) => {
    setBusy(true);
    try {
      await api("/reports", { body: { target_type: targetType, target_id: targetId, reason, details: "" } });
      toast(it ? "Grazie, esamineremo la segnalazione." : "Gracias, revisaremos tu reporte.");
      onClose();
    } catch (e: any) {
      toast(e?.message || "Error", "error");
    } finally {
      setBusy(false);
    }
  };

  const doBlock = async () => {
    if (!blockUserId) return;
    setBusy(true);
    try {
      await api("/blocks", { body: { user_id: blockUserId } });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.invalidateQueries({ queryKey: ["specialists"] });
      queryClient.invalidateQueries({ queryKey: ["reviews"] });
      toast(it ? "Utente bloccato." : "Usuario bloqueado.");
      onClose();
      onBlocked?.();
    } catch (e: any) {
      toast(e?.message || "Error", "error");
    } finally {
      setBusy(false);
    }
  };

  const confirmBlock = () => {
    Alert.alert(
      it ? "Bloccare questo utente?" : "¿Bloquear a este usuario?",
      it
        ? "Non potrete più scrivervi né vedere i contenuti dell'altro."
        : "No podrán escribirse ni ver los contenidos del otro.",
      [
        { text: it ? "Annulla" : "Cancelar", style: "cancel" },
        { text: it ? "Blocca" : "Bloquear", style: "destructive", onPress: doBlock },
      ],
    );
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={() => !busy && onClose()}>
      <Pressable style={styles.backdrop} onPress={() => !busy && onClose()} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]}>
        <View style={styles.handle} />
        <Text style={styles.title}>{it ? "Segnala contenuto" : "Reportar contenido"}</Text>
        <Text style={styles.sub}>{it ? "Perché lo stai segnalando?" : "¿Por qué lo reportas?"}</Text>
        {REASONS.map((r) => (
          <Pressable key={r.key} testID={`report-reason-${r.key}`} disabled={busy} onPress={() => sendReport(r.key)} style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surfaceTertiary }]}>
            <Ionicons name="flag-outline" size={18} color={colors.muted} />
            <Text style={styles.rowText}>{it ? r.it : r.es}</Text>
          </Pressable>
        ))}
        {blockUserId ? (
          <Pressable testID="report-block-user" disabled={busy} onPress={confirmBlock} style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surfaceTertiary }]}>
            <Ionicons name="ban-outline" size={18} color={colors.error} />
            <Text style={[styles.rowText, { color: colors.error }]}>{it ? "Blocca utente" : "Bloquear usuario"}</Text>
          </Pressable>
        ) : null}
        {busy ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 8 }} /> : null}
        <Pressable testID="report-cancel" disabled={busy} onPress={onClose} style={styles.cancel}>
          <Text style={styles.cancelText}>{it ? "Annulla" : "Cancelar"}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((c) => ({
  backdrop: { flex: 1, backgroundColor: c.scrim },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingHorizontal: 20, paddingTop: 12, gap: 4 },
  handle: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, backgroundColor: c.borderStrong, marginBottom: 8 },
  title: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  sub: { fontSize: 14, color: c.muted, marginBottom: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 52, paddingHorizontal: 8, borderRadius: 12 },
  rowText: { fontSize: 16, color: c.onSurface, flex: 1 },
  cancel: { minHeight: 52, alignItems: "center", justifyContent: "center", marginTop: 4 },
  cancelText: { fontSize: 16, fontWeight: "700", color: c.brandPrimary },
}));
