import React, { useEffect, useState } from "react";
import { Linking, Modal, Pressable, ScrollView, Text, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

export type Announcement = { announcement_id: string; type: string; title: string; text: string; link?: string | null; ends_at: string; seen: boolean };

// Como mucho un pop-up por sesion de la app: no se molesta a la persona en cada pantalla.
let shownThisSession = false;

/** Pop-up con novedades, promociones, eventos o sorteos. Se marca como visto al cerrarlo: no vuelve a salir. */
export function AnnouncementPopup() {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const pending = useQuery({ queryKey: ["announcements-pending"], queryFn: () => api<{ items: Announcement[] }>("/announcements/pending") });
  const current = pending.data?.items?.[0];

  useEffect(() => {
    if (current && !shownThisSession) {
      shownThisSession = true;
      setOpen(true);
    }
  }, [current?.announcement_id]);

  if (!current || !open) return null;

  const close = async () => {
    setOpen(false);
    try {
      await api(`/announcements/${current.announcement_id}/seen`, { method: "POST" });
    } catch {}
    qc.invalidateQueries({ queryKey: ["announcements-pending"] });
  };

  const openLink = () => {
    if (current.link) Linking.openURL(current.link).catch(() => {});
    close();
  };

  return (
    <Modal transparent animationType="fade" visible onRequestClose={close}>
      <View style={styles.backdrop}>
        <View style={styles.card} testID="announcement-popup">
          <Text style={styles.kind}>{t(`announce_${current.type}`)}</Text>
          <Text style={styles.title}>{current.title}</Text>
          <ScrollView style={{ maxHeight: 280 }}>
            <Text style={styles.text}>{current.text}</Text>
          </ScrollView>
          <View style={styles.actions}>
            {current.link ? (
              <Pressable testID="announcement-open" onPress={openLink} style={[styles.btn, { backgroundColor: colors.brandPrimary }]}>
                <Text style={[styles.btnText, { color: colors.onBrandPrimary }]}>{t("announce_more")}</Text>
              </Pressable>
            ) : null}
            <Pressable testID="announcement-close" onPress={close} style={[styles.btn, { backgroundColor: colors.surfaceTertiary }]}>
              <Text style={[styles.btnText, { color: colors.onSurfaceSecondary }]}>{t("announce_close")}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((c) => ({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", padding: 24 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 24, padding: 22, gap: 10 },
  kind: { color: c.brandPrimary, fontWeight: "800", fontSize: 13, textTransform: "uppercase" },
  title: { color: c.onSurface, fontWeight: "800", fontSize: 22 },
  text: { color: c.onSurfaceSecondary, fontSize: 15, lineHeight: 22 },
  actions: { gap: 10, marginTop: 8 },
  btn: { borderRadius: 14, paddingVertical: 14, alignItems: "center" },
  btnText: { fontWeight: "800", fontSize: 15 },
}));
