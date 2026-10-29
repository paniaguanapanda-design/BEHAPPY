import { useCallback, useEffect, useState } from "react";
import { storage } from "@/src/utils/storage";

// "NUOVO" badges: shown until the person opens that feature once.
export function useSeen(key: string) {
  const [seen, setSeen] = useState(true);
  const reload = useCallback(() => {
    storage.getItem(`seen_${key}`, false).then((v) => setSeen(Boolean(v)));
  }, [key]);
  useEffect(reload, [reload]);
  const markSeen = useCallback(() => {
    setSeen(true);
    storage.setItem(`seen_${key}`, true);
  }, [key]);
  return { isNew: !seen, markSeen, reload };
}

export async function markSeen(key: string) {
  await storage.setItem(`seen_${key}`, true);
}
