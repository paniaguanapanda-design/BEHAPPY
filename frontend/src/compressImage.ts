import { ImageManipulator, SaveFormat } from "expo-image-manipulator";

const MAX_SIDE = 1024;

/** Resize to max 1024px on the longest side and recompress as JPEG; returns base64 (no data: prefix). */
export async function compressToBase64(uri: string, width?: number, height?: number): Promise<string> {
  const ctx = ImageManipulator.manipulate(uri);
  const w = width ?? 0;
  const h = height ?? 0;
  if (w >= h) {
    if (!w || w > MAX_SIDE) ctx.resize({ width: MAX_SIDE });
  } else if (h > MAX_SIDE) {
    ctx.resize({ height: MAX_SIDE });
  }
  const img = await ctx.renderAsync();
  const res = await img.saveAsync({ compress: 0.6, format: SaveFormat.JPEG, base64: true });
  if (!res.base64) throw new Error("Image compression failed");
  return res.base64.replace(/^data:image\/\w+;base64,/, "");
}
