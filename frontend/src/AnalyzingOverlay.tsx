import React from "react";
import { ActivityIndicator, Modal, Text, View } from "react-native";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

export function AnalyzingOverlay({ visible }: { visible: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  return (
    <Modal visible={visible} transparent animationType="fade">
      <View style={styles.backdrop} testID="analyzing-overlay">
        <View style={styles.card}>
          <ActivityIndicator size="large" color={colors.brandPrimary} />
          <Text style={styles.title}>{t("analyzing")}</Text>
          <Text style={styles.sub}>{t("analyzing_sub")}</Text>
        </View>
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((c) => ({
  backdrop: { flex: 1, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center", padding: 24 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: 20, padding: 32, alignItems: "center", gap: 12, width: "100%", maxWidth: 340 },
  title: { fontSize: 20, fontWeight: "700", color: c.onSurface },
  sub: { fontSize: 14, color: c.muted, textAlign: "center" },
}));
