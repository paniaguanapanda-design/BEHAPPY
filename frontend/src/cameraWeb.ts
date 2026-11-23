// expo-camera on the web opens the camera without asking for a size, so phone browsers usually give 640x480 and
// the photo is taken from that small frame (soft, little detail for the AI). Once the camera is running, ask the
// same video track for Full HD and continuous focus. Does nothing outside the browser or if the browser refuses.

type Track = {
  applyConstraints: (c: object) => Promise<void>;
  getCapabilities?: () => { focusMode?: string[] };
  getSettings: () => { width?: number; height?: number };
};

export async function upgradeWebCamera(root?: { querySelectorAll: (s: string) => ArrayLike<unknown> }): Promise<{ width: number; height: number } | null> {
  const scope = root ?? (typeof document !== "undefined" ? document : null);
  if (!scope) return null;
  for (const v of Array.from(scope.querySelectorAll("video")) as { srcObject?: { getVideoTracks?: () => Track[] } | null }[]) {
    const track = v.srcObject?.getVideoTracks?.()[0];
    if (!track) continue;
    try {
      await track.applyConstraints({ width: { ideal: 1920 }, height: { ideal: 1080 } });
    } catch {
      // keep the current size
    }
    if (track.getCapabilities?.().focusMode?.includes("continuous")) {
      try {
        await track.applyConstraints({ advanced: [{ focusMode: "continuous" }] });
      } catch {
        // keep the browser's focus
      }
    }
    const s = track.getSettings();
    return { width: s.width ?? 0, height: s.height ?? 0 };
  }
  return null;
}
