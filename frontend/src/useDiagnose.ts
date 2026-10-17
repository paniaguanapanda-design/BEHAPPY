import { useState } from "react";
import { useRouter } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";

export function useDiagnose() {
  const [analyzing, setAnalyzing] = useState(false);
  const router = useRouter();
  const { lang, t } = useI18n();
  const toast = useToast();

  const run = async (base64: string, replace = false) => {
    setAnalyzing(true);
    try {
      const d = await api<{ diagnosis_id: string }>("/diagnose", { body: { image_base64: base64, language: lang } });
      queryClient.invalidateQueries({ queryKey: ["diagnoses"] });
      const target = { pathname: "/diagnosis/[id]" as const, params: { id: d.diagnosis_id } };
      if (replace) router.replace(target);
      else router.push(target);
    } catch (e: any) {
      toast(e?.message || t("error_generic"), "error");
    } finally {
      setAnalyzing(false);
    }
  };

  const pickFromGallery = async (replace = false) => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], base64: true, quality: 0.5 });
    if (!res.canceled && res.assets[0]?.base64) await run(res.assets[0].base64, replace);
  };

  return { analyzing, run, pickFromGallery };
}
