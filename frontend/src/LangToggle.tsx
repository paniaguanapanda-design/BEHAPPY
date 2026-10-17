import React from "react";
import { Pressable, Text, View } from "react-native";
import { useI18n, Lang } from "@/src/i18n";
import { makeStyles } from "@/src/theme";

export function LangToggle({ dark }: { dark?: boolean }) {
  const styles = useStyles();
  const { lang, setLang } = useI18n();
  return (
    <View style={[styles.wrap, dark && styles.wrapDark]}>
      {(["es", "it"] as Lang[]).map((l) => (
        <Pressable key={l} testID={`lang-toggle-${l}`} onPress={() => setLang(l)} style={[styles.item, lang === l && styles.itemOn]}>
          <Text style={[styles.text, dark && styles.textDark, lang === l && styles.textOn]}>{l === "es" ? "ES" : "IT"}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: { flexDirection: "row", backgroundColor: c.surfaceTertiary, borderRadius: 999, padding: 3 },
  wrapDark: { backgroundColor: c.scrim },
  item: { paddingHorizontal: 14, minHeight: 34, justifyContent: "center", borderRadius: 999 },
  itemOn: { backgroundColor: c.surfaceSecondary },
  text: { fontSize: 13, fontWeight: "700", color: c.onSurfaceTertiary },
  textDark: { color: c.onSurfaceInverse },
  textOn: { color: c.brandPrimary },
}));
