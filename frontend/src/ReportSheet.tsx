import React, { useState } from "react";
import { ActivityIndicator, Alert, Modal, Pressable, Text, TextInput, View } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
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
  reasons?: Reason[];
  targetName?: string; // "Segnala Marco Rossi"
};

type Reason = { key: string; es: string; it: string };

// Reasons for a hardware store on the map (3 reports from different users hide it until reviewed).
export const STORE_REASONS: Reason[] = [
  { key: "not_exists", es: "No existe o ha cerrado", it: "Non esiste o ha chiuso" },
  { key: "not_store", es: "No es una ferretería", it: "Non è una ferramenta" },
  { key: "wrong_info", es: "Dirección u horario incorrectos", it: "Indirizzo o orari sbagliati" },
  { key: "other", es: "Otro motivo", it: "Altro motivo" },
];

// A client reports a specialist (3 clients who talked with him hide the profile until reviewed).
export const SPECIALIST_REASONS: Reason[] = [
  { key: "no_show", es: "No se presentó a la cita", it: "Non si è presentato all'appuntamento" },
  { key: "broke_agreement", es: "No cumplió lo acordado", it: "Non ha rispettato quanto concordato" },
  { key: "overcharged", es: "Pidió más dinero de lo acordado", it: "Ha chiesto più soldi del concordato" },
  { key: "bad_work", es: "Trabajo mal hecho o peligroso", it: "Lavoro fatto male o pericoloso" },
  { key: "harassment", es: "Maleducado, acoso o amenazas", it: "Maleducato, molestie o minacce" },
  { key: "fraud", es: "Estafa o perfil falso", it: "Truffa o profilo falso" },
];

const REASONS: Reason[] = [
  { key: "inappropriate", es: "Contenido inapropiado u ofensivo", it: "Contenuto inappropriato o offensivo" },
  { key: "harassment", es: "Acoso o amenazas", it: "Molestie o minacce" },
  { key: "fraud", es: "Estafa o engaño", it: "Truffa o inganno" },
  { key: "spam", es: "Spam o publicidad", it: "Spam o pubblicità" },
  { key: "other", es: "Otro motivo", it: "Altro motivo" },
];

export function ReportSheet({ visible, onClose, targetType, targetId, blockUserId, onBlocked, reasons = REASONS, targetName }: Props) {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { lang } = useI18n();
  const toast = useToast();
  const it = lang === "it";
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  const [details, setDetails] = useState("");
  const isSpecialist = targetType === "specialist";

  const close = () => {
    setReason(null);
    setDetails("");
    onClose();
  };

  const sendReport = async () => {
    if (!reason) return;
    setBusy(true);
    try {
      await api("/reports", { body: { target_type: targetType, target_id: targetId, reason, details: details.trim() } });
      setReason(null);
      setDetails("");
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
      close();
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
    <Modal visible={visible} transparent animationType="slide" onRequestClose={() => !busy && close()}>
      <Pressable style={styles.backdrop} onPress={() => !busy && close()} />
      <KeyboardAvoidingView behavior="padding">
        <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]}>
          <View style={styles.handle} />
          <Text style={styles.title}>
            {targetName ? `${it ? "Segnala" : "Reportar a"} ${targetName}` : it ? "Segnala contenuto" : "Reportar contenido"}
          </Text>
          <Text style={styles.sub}>
            {isSpecialist
              ? it
                ? "Cosa è successo? Lo leggiamo noi, lo specialista non sa chi l'ha segnalato."
                : "¿Qué pasó? Lo leemos nosotros; el especialista no sabe quién lo reportó."
              : it
                ? "Cosa è successo? Lo leggiamo noi."
                : "¿Qué pasó? Lo leemos nosotros."}
          </Text>
          {reasons.map((r) => {
            const on = reason === r.key;
            return (
              <Pressable
                key={r.key}
                testID={`report-reason-${r.key}`}
                disabled={busy}
                onPress={() => setReason(r.key)}
                style={styles.opt}
                accessibilityRole="radio"
                accessibilityState={{ checked: on }}
              >
                <View style={[styles.radio, on && styles.radioOn]} />
                <Text style={styles.rowText}>{it ? r.it : r.es}</Text>
              </Pressable>
            );
          })}
          <TextInput
            testID="report-details"
            style={styles.details}
            placeholder={it ? "Racconta cosa è successo (facoltativo)" : "Cuéntanos qué pasó (opcional)"}
            placeholderTextColor={colors.muted}
            value={details}
            onChangeText={setDetails}
            multiline
            maxLength={1000}
          />
          <Pressable
            testID="report-send"
            disabled={busy || !reason}
            onPress={sendReport}
            style={({ pressed }) => [styles.send, (!reason || busy) && { opacity: 0.5 }, pressed && { transform: [{ scale: 0.98 }] }]}
          >
            {busy ? <ActivityIndicator color={colors.onSurfaceInverse} /> : <Text style={styles.sendText}>{it ? "Invia segnalazione" : "Enviar reporte"}</Text>}
          </Pressable>
          {blockUserId ? (
            <Pressable testID="report-block-user" disabled={busy} onPress={confirmBlock} style={styles.block}>
              <Ionicons name="ban-outline" size={16} color={colors.error} />
              <Text style={styles.blockText}>{it ? "Blocca utente" : "Bloquear usuario"}</Text>
            </Pressable>
          ) : null}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const useStyles = makeStyles((c) => ({
  backdrop: { flex: 1, backgroundColor: c.scrim },
  sheet: { backgroundColor: c.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: 18, paddingTop: 10, gap: 2 },
  handle: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, backgroundColor: c.border, marginBottom: 8 },
  title: { fontSize: 18, fontFamily: fonts.display, color: c.onSurface },
  sub: { fontSize: 13, color: c.muted, marginBottom: 4, lineHeight: 18 },
  opt: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 48, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: "#EEF1F5" },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: "#C5CDD8" },
  radioOn: { borderWidth: 6, borderColor: c.brandPrimary },
  rowText: { fontSize: 15, color: c.onSurface, flex: 1 },
  details: { minHeight: 64, maxHeight: 120, borderRadius: 12, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface, padding: 12, fontSize: 14, color: c.onSurface, marginTop: 10, textAlignVertical: "top" },
  send: { minHeight: 50, borderRadius: 999, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center", marginTop: 12 },
  sendText: { color: c.onSurfaceInverse, fontSize: 16, fontWeight: "700" },
  block: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, minHeight: 44, marginTop: 4 },
  blockText: { fontSize: 14, fontWeight: "600", color: c.error },
}));
