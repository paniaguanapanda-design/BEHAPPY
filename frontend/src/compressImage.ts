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

/** Shrink a photo before uploading it (profile, past work, ID document): max 1600 px on the longest side, JPEG.
 *  Phone photos are often 5-10 MB, which made uploads very slow. Falls back to the original if anything fails. */
export async function shrinkForUpload(uri: string, maxSide = 1600): Promise<string> {
  try {
    const original = await ImageManipulator.manipulate(uri).renderAsync();
    const { width, height } = original;
    const ctx = ImageManipulator.manipulate(uri);
    if (width >= height && width > maxSide) ctx.resize({ width: maxSide });
    else if (height > width && height > maxSide) ctx.resize({ height: maxSide });
    const img = await ctx.renderAsync();
    const res = await img.saveAsync({ compress: 0.75, format: SaveFormat.JPEG });
    return res.uri;
  } catch {
    return uri;
  }
}
