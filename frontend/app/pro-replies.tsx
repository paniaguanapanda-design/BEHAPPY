import React, { useEffect, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { makeStyles, useTheme, fonts } from "@/src/theme";
import { Button } from "@/src/ui";
import { markSeen } from "@/src/seen";

const MAX = 10;

// Saved messages the specialist taps in the chat to answer in a second.
export default function ProReplies() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, lang } = useI18n();
  const toast = useToast();
  const q = useQuery({ queryKey: ["pro-settings", lang], queryFn: () => api<any>(`/specialists/me/settings?lang=${lang}`) });
  const [items, setItems] = useState<string[] | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    markSeen("pro_replies");
  }, []);
  useEffect(() => {
    if (q.data && items === null) setItems(q.data.quick_replies);
  }, [q.data, items]);

  const save = async (next: string[]) => {
    setItems(next);
    setBusy(true);
    try {
      await api("/specialists/me/quick-replies", { method: "PUT", body: { items: next } });
      queryClient.invalidateQueries({ queryKey: ["pro-settings"] });
    } catch (e: any) {
      toast(e.message || t("error_generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  const add = () => {
    const v = draft.trim();
    if (!v || !items) return;
    if (items.length >= MAX) return toast(t("replies_max"), "error");
    setDraft("");
    save([...items, v]);
  };

  return (
    <View style={styles.root}>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="replies-back" onPress={() => router.back()} style={styles.back} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("quick_replies")}</Text>
      </View>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 24 }]} keyboardShouldPersistTaps="handled">
        <Text style={styles.note}>{t("replies_note")}</Text>
        <View style={styles.group}>
          {(items || []).map((r, i) => (
            <View key={`${i}-${r}`} style={[styles.row, i > 0 && styles.rowSep]}>
              <Ionicons name="flash" size={16} color={colors.brandPrimary} />
              <Text style={styles.rowText}>{r}</Text>
              <Pressable
                testID={`reply-delete-${i}`}
                hitSlop={8}
                disabled={busy}
                onPress={() => save(items!.filter((_, j) => j !== i))}
                accessibilityLabel={t("delete")}
                style={styles.del}
              >
                <Ionicons name="close" size={18} color={colors.muted} />
              </Pressable>
            </View>
          ))}
          {items && !items.length ? <Text style={[styles.note, { padding: 14 }]}>{t("replies_empty")}</Text> : null}
        </View>
        <TextInput
          testID="reply-input"
          style={styles.input}
          placeholder={t("replies_add_ph")}
          placeholderTextColor={colors.muted}
          value={draft}
          onChangeText={setDraft}
          maxLength={200}
          onSubmitEditing={add}
          returnKeyType="done"
        />
        <Button testID="reply-add" title={t("replies_add")} icon="add" onPress={add} disabled={!draft.trim() || busy} />
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  top: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 4 },
  back: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontFamily: fonts.display, color: c.onSurface },
  body: { padding: 16, gap: 14 },
  note: { fontSize: 14, color: c.muted, lineHeight: 20 },
  group: { backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderRadius: 14, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingLeft: 14, minHeight: 52 },
  rowSep: { borderTopWidth: 1, borderTopColor: c.divider },
  rowText: { flex: 1, fontSize: 15, color: c.onSurface, paddingVertical: 12 },
  del: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  input: { height: 52, borderRadius: 14, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, paddingHorizontal: 16, fontSize: 16, color: c.onSurface },
}));
