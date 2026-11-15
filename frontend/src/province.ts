import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { queryClient } from "@/src/query-client";

// BeHappy works in any country: clients see and contact the specialists whose work radius reaches them.
export type Province = { code: string; name: string };
export type Place = { name: string; province: Province; lat: number; lng: number };

export function useMyProvince() {
  return useQuery({ queryKey: ["my-zone"], queryFn: () => api<{ province: Province | null }>("/me/zone") });
}

// The server works out the province of the point (GPS or the chosen comune) and keeps it.
export async function saveMyProvince(lat: number, lng: number): Promise<Province> {
  const r = await api<{ province: Province }>("/me/zone", { method: "PUT", body: { lat, lng } });
  queryClient.setQueryData(["my-zone"], r);
  queryClient.invalidateQueries({ queryKey: ["specialists"] });
  queryClient.invalidateQueries({ queryKey: ["specialist"] });
  return r.province;
}

export const provinceLabel = (p: Province, t: (k: string) => string) => t("prov_of").replace("{p}", p.name);
