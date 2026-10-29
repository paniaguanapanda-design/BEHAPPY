import { useState } from "react";
import { useRouter } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { compressToBase64 } from "@/src/compressImage";
import { localPhotos } from "@/src/localPhotos";
import { lastPositionIfAllowed } from "@/src/position";

export function useDiagnose() {
  const [analyzing, setAnalyzing] = useState(false);
  const router = useRouter();
  const { lang, t } = useI18n();
  const toast = useToast();

  const run = async (uri: string, width?: number, height?: number, replace = false): Promise<boolean> => {
    setAnalyzing(true);
    try {
      const [base64, pos] = await Promise.all([compressToBase64(uri, width, height), lastPositionIfAllowed()]);
      // The position (only if already allowed) lets nearby specialists of that trade get an alert; it is not shown to anyone.
      const d = await api<{ diagnosis_id: string }>("/diagnose", { body: { image_base64: base64, language: lang, ...(pos ?? {}) } });
      localPhotos[d.diagnosis_id] = uri;
      // show the result straight away in the scanner's language — no extra fetch/translation
      queryClient.setQueryData(["diagnosis", d.diagnosis_id, lang], { ...d, title: (d as any)[`title_${lang}`] });
      queryClient.invalidateQueries({ queryKey: ["diagnoses"] });
      const target = { pathname: "/diagnosis/[id]" as const, params: { id: d.diagnosis_id } };
      if (replace) router.replace(target);
      else router.push(target);
      return true;
    } catch (e: any) {
      toast(e?.message || t("error_generic"), "error");
      return false;
    } finally {
      setAnalyzing(false);
    }
  };

  const pickFromGallery = async (replace = false) => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 1 });
    const a = res.canceled ? null : res.assets[0];
    if (a) return await run(a.uri, a.width, a.height, replace);
    return false;
  };

  return { analyzing, run, pickFromGallery };
}
