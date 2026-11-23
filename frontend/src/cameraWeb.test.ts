import { describe, expect, it } from "@jest/globals";
import { upgradeWebCamera } from "./cameraWeb";

function fakeTrack(focusModes?: string[], refuseSize = false) {
  const applied: object[] = [];
  let size = { width: 640, height: 480 };
  const track = {
    applied,
    applyConstraints: async (c: any) => {
      applied.push(c);
      if (c.width) {
        if (refuseSize) throw new Error("OverconstrainedError");
        size = { width: 1920, height: 1080 };
      }
    },
    getCapabilities: () => (focusModes ? { focusMode: focusModes } : {}),
    getSettings: () => size,
  };
  return track;
}
const page = (...tracks: ReturnType<typeof fakeTrack>[]) => ({
  querySelectorAll: () => tracks.map((t) => ({ srcObject: { getVideoTracks: () => [t] } })),
});

describe("upgradeWebCamera", () => {
  it("asks the camera for Full HD and continuous focus", async () => {
    const t = fakeTrack(["manual", "continuous"]);
    expect(await upgradeWebCamera(page(t))).toEqual({ width: 1920, height: 1080 });
    expect(t.applied).toEqual([
      { width: { ideal: 1920 }, height: { ideal: 1080 } },
      { advanced: [{ focusMode: "continuous" }] },
    ]);
  });

  it("does not ask for a focus mode the camera does not have", async () => {
    const t = fakeTrack(["manual"]);
    await upgradeWebCamera(page(t));
    expect(t.applied).toHaveLength(1);
  });

  it("keeps working when the browser refuses the size", async () => {
    const t = fakeTrack(["continuous"], true);
    expect(await upgradeWebCamera(page(t))).toEqual({ width: 640, height: 480 });
  });

  it("does nothing when there is no camera on the page", async () => {
    expect(await upgradeWebCamera({ querySelectorAll: () => [] })).toBeNull();
  });
});
