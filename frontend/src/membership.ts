import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";

export type Plan = "monthly" | "yearly";
export type Membership = { active: boolean; plan: Plan | null; source: string | null; expires_at: string | null; plans: Record<Plan, number> };

export const useMembership = (enabled = true) =>
  useQuery({ queryKey: ["membership"], queryFn: () => api<Membership>("/membership/me"), enabled });
