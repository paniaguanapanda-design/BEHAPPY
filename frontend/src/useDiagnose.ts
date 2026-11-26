import { useState } from "react";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { api } from "@/src/api";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { queryClient } from "@/src/query-client";
import { compressToBase64 } from "@/src/compressImage";
import { localPhotos } from "@/src/localPhotos";
import { lastPositionIfAllowed } from "@/src/position";

let pendingScanNote = "";

export function setPendingScanNote(note: string) {
  pendingScanNote = note;
}

export function takePendingScanNote() {
  const note = pendingScanNote;
  pendingScanNote = "";
  return note;
}

export type DiagnoseQuota = { limit: number; used: number; remaining: number; resets_at: string };

export function useDiagnose() {
  const [analyzing, setAnalyzing] = useState(false);
  const router = useRouter();
  const { lang, t } = useI18n();
  const toast = useToast();
  // Cuota mensual: cuantos diagnosticos le quedan a la persona (ver backend, /diagnoses/quota).
  const quotaQuery = useQuery({ queryKey: ["diag-quota"], queryFn: () => api<DiagnoseQuota>("/diagnoses/quota") });
  const quota = quotaQuery.data;

  const quotaReachedMessage = (q: DiagnoseQuota) => {
    const date = new Date(q.resets_at).toLocaleDateString(lang === "it" ? "it-IT" : lang === "en" ? "en-GB" : "es-ES", { day: "numeric", month: "long" });
    return t("quota_reached").replace("{limit}", String(q.limit)).replace("{date}", date);
  };

  const run = async (uri: string | null, width?: number, height?: number, replace = false, note?: string): Promise<boolean> => {
    const description = note?.trim();
    if (!uri && !description) {
      toast(t("request_note_required"), "error");
      return false;
    }
    if (quota && quota.remaining <= 0) {
      toast(quotaReachedMessage(quota), "error");
      return false;
    }
    setAnalyzing(true);
    try {
      const [base64, pos] = await Promise.all([
        uri ? compressToBase64(uri, width, height) : Promise.resolve(null),
        lastPositionIfAllowed(),
      ]);
      // The position (only if already allowed) lets nearby specialists of that trade get an alert; it is not shown to anyone.
      const d = await api<{ diagnosis_id: string }>("/diagnose", {
        body: { ...(base64 ? { image_base64: base64 } : {}), ...(description ? { note: description } : {}), language: lang, ...(pos ?? {}) },
      });
      if (uri) localPhotos[d.diagnosis_id] = uri;
      // The server answers at once with the id and analyses in the background; the diagnosis screen polls it.
      queryClient.invalidateQueries({ queryKey: ["diagnoses"] });
      queryClient.invalidateQueries({ queryKey: ["diag-quota"] });
      const target = { pathname: "/diagnosis/[id]" as const, params: { id: d.diagnosis_id } };
      if (replace) router.replace(target);
      else router.push(target);
      return true;
    } catch (e: any) {
      if (e?.message === "monthly_limit") {
        // El servidor ya no deja: refresca la cuota y explica cuando se renueva.
        const fresh = await quotaQuery.refetch();
        toast(fresh.data ? quotaReachedMessage(fresh.data) : t("quota_reached_short"), "error");
      } else {
        toast(e?.message || t("error_generic"), "error");
      }
      return false;
    } finally {
      setAnalyzing(false);
    }
  };

  const pickFromGallery = async (replace = false, note?: string) => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 1 });
    const a = res.canceled ? null : res.assets[0];
    if (a) return await run(a.uri, a.width, a.height, replace, note);
    return false;
  };

  return { analyzing, run, pickFromGallery, quota };
}
