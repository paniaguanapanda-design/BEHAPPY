import React, { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { api, imageUri } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";
import { DifficultyBadge } from "@/src/DifficultyBadge";
import { localPhotos } from "@/src/localPhotos";
import { Button, Loading, SectionTitle } from "@/src/ui";

export default function Diagnosis() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, lang } = useI18n();
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useQuery({ queryKey: ["diagnosis", id, lang], queryFn: () => api<any>(`/diagnoses/${id}?lang=${lang}`) });
  const [done, setDone] = useState<Record<number, boolean>>({});

  if (q.isLoading) return <Loading />;
  const d = q.data;
  if (!d)
    return (
      <View style={[styles.root, { alignItems: "center", justifyContent: "center", gap: 12 }]}>
        <Text style={styles.body}>{t("error_generic")}</Text>
        <Button title={t("retry")} onPress={() => q.refetch()} testID="diagnosis-retry-button" />
      </View>
    );

  const steps: { title: string; detail: string }[] = d.difficulty === "expert" ? [] : d.steps || [];
  const isAppliance = d.category === "appliance";
  const photo = localPhotos[d.diagnosis_id] ?? imageUri(d.image_path);
  const materials: any[] = d.difficulty === "expert" ? [] : d.materials || [];
  const tools: string[] = d.difficulty === "expert" ? [] : d.tools || [];
  const doneCount = Object.values(done).filter(Boolean).length;
  const goPro = () => router.push({ pathname: "/specialists", params: { category: d.category } });

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}>
        <View style={styles.hero}>
          {photo ? (
            <Image source={{ uri: photo }} style={styles.abs} contentFit="cover" testID="diagnosis-photo" />
          ) : (
            <View style={[styles.abs, { backgroundColor: colors.surfaceInverse }]} />
          )}
          <LinearGradient colors={["transparent", colors.surfaceInverse]} style={styles.abs} />
          <Pressable testID="diagnosis-back-button" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} style={[styles.back, { top: insets.top + 8 }]}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurfaceInverse} />
          </Pressable>
          <View style={styles.heroContent}>
            <View style={styles.tagRow}>
              <View style={styles.catTag}>
                <Text style={styles.catText}>{t(`cat_${d.category}`)}</Text>
              </View>
              {!isAppliance && <DifficultyBadge level={d.difficulty} large />}
            </View>
            <Text style={styles.title} testID="diagnosis-title">
              {d.title}
            </Text>
          </View>
        </View>

        <View style={styles.content}>
          <Text style={styles.body} testID="diagnosis-description">
            {d.description}
          </Text>

          {d.is_home_problem === false ? (
            <View style={styles.warnBox}>
              <Text style={styles.warnText}>{t("not_home")}</Text>
              <Button title={t("scan_again")} icon="camera" onPress={() => router.replace("/scan")} testID="scan-again-button" />
            </View>
          ) : isAppliance ? (
            <View style={styles.outcome} testID="outcome-appliance">
              <Ionicons name="swap-horizontal" size={22} color={colors.brandTertiary} />
              <Text style={styles.outcomeText}>{t("appliance_hint")}</Text>
            </View>
          ) : (
            <>
              {d.estimated_time && d.difficulty !== "expert" ? (
                <View style={styles.metaRow}>
                  <View style={styles.meta}>
                    <Ionicons name="time-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.metaLabel}>{t("time")}</Text>
                    <Text style={styles.metaValue}>{d.estimated_time}</Text>
                  </View>
                </View>
              ) : null}

              {d.difficulty === "expert" && (
                <View style={styles.outcome} testID="outcome-expert">
                  <Ionicons name="shield-half" size={22} color={colors.error} />
                  <Text style={styles.outcomeText}>{t("expert_hint")}</Text>
                  <Button title={t("see_specialists")} icon="people" onPress={goPro} testID="see-specialists-button" />
                </View>
              )}
              {d.difficulty === "medium" && (
                <View style={styles.outcome} testID="outcome-medium">
                  <Ionicons name="construct" size={22} color={colors.warning} />
                  <Text style={styles.outcomeText}>{t("medium_hint")}</Text>
                </View>
              )}
              {d.difficulty === "easy" && (
                <View style={styles.outcome} testID="outcome-easy">
                  <Ionicons name="hammer" size={22} color={colors.success} />
                  <Text style={styles.outcomeText}>{t("easy_hint")}</Text>
                </View>
              )}

              {d.safety_warnings?.length > 0 && (
                <View style={styles.safety} testID="safety-warnings">
                  <View style={styles.safetyHead}>
                    <Ionicons name="warning" size={18} color={colors.warning} />
                    <Text style={styles.safetyTitle}>{t("safety")}</Text>
                  </View>
                  {d.safety_warnings.map((w: string, i: number) => (
                    <Text key={i} style={styles.safetyText}>
                      • {w}
                    </Text>
                  ))}
                </View>
              )}

              {materials.length > 0 && (
                <>
                  <SectionTitle>{t("materials")}</SectionTitle>
                  <View style={styles.card} testID="materials-list">
                    {materials.map((m: any, i: number) => (
                      <View key={i} style={[styles.matRow, i > 0 && styles.divider]}>
                        <Ionicons name="cube-outline" size={18} color={colors.brandTertiary} />
                        <Text style={styles.matName}>{m.name}</Text>
                        <Text style={styles.matQty}>{m.quantity}</Text>
                      </View>
                    ))}
                  </View>
                </>
              )}

              {tools.length > 0 && (
                <>
                  <SectionTitle>{t("tools")}</SectionTitle>
                  <View style={styles.toolWrap}>
                    {tools.map((tool: string, i: number) => (
                      <View key={i} style={styles.tool}>
                        <Ionicons name="build-outline" size={14} color={colors.onBrandSecondary} />
                        <Text style={styles.toolText}>{tool}</Text>
                      </View>
                    ))}
                  </View>
                </>
              )}

              {steps.length > 0 && (
              <View style={{ gap: 12 }}>
                <View style={styles.stepsHead}>
                  <SectionTitle>{t("steps")}</SectionTitle>
                  <Text style={styles.progress} testID="steps-progress">
                    {doneCount}/{steps.length}
                  </Text>
                </View>
                {steps.map((s, i) => (
                  <Pressable key={i} testID={`step-item-${i}`} onPress={() => setDone((p) => ({ ...p, [i]: !p[i] }))} style={[styles.step, done[i] && styles.stepDone]}>
                    <View style={[styles.stepNum, done[i] && { backgroundColor: colors.success }]}>
                      {done[i] ? <Ionicons name="checkmark" size={16} color={colors.onSuccess} /> : <Text style={styles.stepNumText}>{i + 1}</Text>}
                    </View>
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text style={[styles.stepTitle, done[i] && styles.strike]}>{s.title}</Text>
                      <Text style={styles.stepDetail}>{s.detail}</Text>
                    </View>
                  </Pressable>
                ))}
              </View>
              )}

              {d.difficulty === "medium" ? (
                <View style={styles.proBox} testID="medium-pro-box">
                  <Text style={styles.proTitle}>{t("when_pro")}</Text>
                  {d.when_to_call_pro ? <Text style={styles.proText}>{d.when_to_call_pro}</Text> : null}
                  <Button title={t("see_specialists")} icon="people" onPress={goPro} testID="see-specialists-button" />
                </View>
              ) : null}
            </>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  abs: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  hero: { height: 320, justifyContent: "flex-end" },
  back: { position: "absolute", left: 16, width: 44, height: 44, borderRadius: 22, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center" },
  heroContent: { padding: 24, gap: 12 },
  tagRow: { flexDirection: "row", gap: 8, alignItems: "center" },
  catTag: { backgroundColor: c.brandSecondary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999 },
  catText: { color: c.onBrandSecondary, fontWeight: "700", fontSize: 13 },
  title: { color: c.onSurfaceInverse, fontSize: 28, fontWeight: "800", letterSpacing: -0.6 },
  content: { padding: 16, gap: 24 },
  outcome: { padding: 16, borderRadius: 16, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 10 },
  outcomeText: { fontSize: 15, color: c.onSurface, lineHeight: 22 },
  body: { fontSize: 16, lineHeight: 24, color: c.onSurfaceTertiary },
  warnBox: { padding: 16, borderRadius: 12, backgroundColor: c.surfaceTertiary, gap: 12 },
  warnText: { color: c.onSurface, fontSize: 15 },
  metaRow: { flexDirection: "row", gap: 12 },
  meta: { flex: 1, padding: 16, borderRadius: 12, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 4 },
  metaLabel: { fontSize: 12, color: c.muted, fontWeight: "600" },
  metaValue: { fontSize: 16, color: c.onSurface, fontWeight: "700" },
  safety: { padding: 16, borderRadius: 12, backgroundColor: c.surfaceTertiary, borderLeftWidth: 4, borderLeftColor: c.warning, gap: 6 },
  safetyHead: { flexDirection: "row", alignItems: "center", gap: 8 },
  safetyTitle: { fontWeight: "700", fontSize: 16, color: c.onSurface },
  safetyText: { color: c.onSurfaceTertiary, fontSize: 14, lineHeight: 20 },
  choiceRow: { flexDirection: "row", gap: 12, marginTop: -12 },
  choice: { flex: 1, padding: 16, borderRadius: 20, backgroundColor: c.surfaceSecondary, borderWidth: 1.5, borderColor: c.border, gap: 6, minHeight: 150 },
  choiceOn: { borderColor: c.brandPrimary },
  recTag: { alignSelf: "flex-start", backgroundColor: c.brandPrimary, color: c.onBrandPrimary, fontSize: 11, fontWeight: "700", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  choiceTitle: { fontSize: 16, fontWeight: "800", color: c.onSurface },
  choiceSub: { fontSize: 13, color: c.muted, lineHeight: 18 },
  card: { borderRadius: 12, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, marginTop: -12 },
  matRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14 },
  divider: { borderTopWidth: 1, borderTopColor: c.divider },
  matName: { flex: 1, fontSize: 15, color: c.onSurface },
  matQty: { fontSize: 13, color: c.muted, fontWeight: "600", maxWidth: 120, textAlign: "right" },
  toolWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: -12 },
  tool: { flexDirection: "row", gap: 6, alignItems: "center", backgroundColor: c.brandSecondary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999 },
  toolText: { color: c.onBrandSecondary, fontSize: 13, fontWeight: "600" },
  stepsHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  progress: { color: c.brandTertiary, fontWeight: "700", fontSize: 15 },
  diyBanner: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: 12, backgroundColor: c.brandSecondary },
  diyText: { color: c.onBrandSecondary, fontSize: 13, flex: 1, fontWeight: "600" },
  step: { flexDirection: "row", gap: 12, padding: 16, borderRadius: 12, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  stepDone: { backgroundColor: c.brandSecondary, borderColor: c.brandSecondary },
  stepNum: { width: 30, height: 30, borderRadius: 15, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  stepNumText: { color: c.onBrandPrimary, fontWeight: "800" },
  stepTitle: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  strike: { textDecorationLine: "line-through", color: c.muted },
  stepDetail: { fontSize: 14, color: c.onSurfaceTertiary, lineHeight: 20 },
  proBox: { padding: 16, borderRadius: 20, backgroundColor: c.surfaceTertiary, gap: 8 },
  proTitle: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  proText: { fontSize: 14, color: c.onSurfaceTertiary, lineHeight: 20, marginBottom: 8 },
}));
