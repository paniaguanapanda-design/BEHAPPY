import React from "react";
import { Text, View } from "react-native";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

export function difficultyColor(level: string, colors: ReturnType<typeof useTheme>["colors"]) {
  return level === "easy" ? colors.success : level === "medium" ? colors.brandTertiary : level === "hard" ? colors.warning : colors.error;
}

export function DifficultyBadge({ level, large }: { level: string; large?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const color = difficultyColor(level, colors);
  return (
    <View style={[styles.badge, { backgroundColor: color }, large && styles.large]} testID="difficulty-badge">
      <Text style={[styles.text, large && { fontSize: 14 }]}>{t(`diff_${level}`)}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  large: { paddingHorizontal: 14, paddingVertical: 6 },
  text: { color: c.onSuccess, fontWeight: "700", fontSize: 12 },
}));
