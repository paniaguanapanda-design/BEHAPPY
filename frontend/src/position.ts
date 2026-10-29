import { useEffect, useState } from "react";
import * as Location from "expo-location";

export type Pos = { lat: number; lng: number };

// The phone position, only when the user already allowed it (never asks by itself; `request` asks).
export function useMyPosition() {
  const [perm, requestPerm] = Location.useForegroundPermissions();
  const [pos, setPos] = useState<Pos | null>(null);

  useEffect(() => {
    if (!perm?.granted || pos) return;
    let cancelled = false;
    (async () => {
      try {
        const last = await Location.getLastKnownPositionAsync();
        if (last && !cancelled) setPos({ lat: last.coords.latitude, lng: last.coords.longitude });
        if (!last) {
          const now = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
          if (!cancelled) setPos({ lat: now.coords.latitude, lng: now.coords.longitude });
        }
      } catch {}
    })();
    return () => {
      cancelled = true;
    };
  }, [perm?.granted, pos]);

  return { pos, granted: !!perm?.granted, canAsk: perm?.canAskAgain !== false, request: requestPerm, ready: perm != null };
}

// One-shot read for a request body (e.g. the diagnosis): null when the permission was not given.
export async function lastPositionIfAllowed(): Promise<Pos | null> {
  try {
    const p = await Location.getForegroundPermissionsAsync();
    if (!p.granted) return null;
    const last = await Location.getLastKnownPositionAsync({ maxAge: 30 * 60 * 1000 });
    return last ? { lat: last.coords.latitude, lng: last.coords.longitude } : null;
  } catch {
    return null;
  }
}
