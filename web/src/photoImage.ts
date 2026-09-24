/**
 * A photo as it is sent: upright, the whole frame, 2048 px on the long edge, JPEG at 0.85.
 *
 * Every number here was measured in `experiments/photo-capture/`. The whole frame, because a square
 * crop cut the very sentences worth keeping — correct sentences fell from 98% to about 70%. 2048 px
 * because at 1280 Cloud Vision's character error on a book photo rose from 0.4% to 2.3%, while the
 * full sensor bought little for three times the bytes. Drawing through a canvas also drops the
 * camera's EXIF, location included, before anything leaves the device; the server strips it again
 * from anything that arrives some other way.
 *
 * Its own module so a test can replace it: jsdom has neither `createImageBitmap` nor a canvas that
 * encodes.
 */

export const LONG_EDGE = 2048;
export const QUALITY = 0.85;

export async function encodePhoto(source: Blob | HTMLCanvasElement): Promise<Blob> {
  const bitmap = source instanceof Blob
    ? await createImageBitmap(source, { imageOrientation: "from-image" })
    : source;
  const scale = Math.min(1, LONG_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser cannot prepare a photo.");
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  if ("close" in bitmap) bitmap.close();
  return new Promise((resolve, reject) => canvas.toBlob(
    (blob) => (blob ? resolve(blob) : reject(new Error("This browser could not prepare the photo."))),
    "image/jpeg",
    QUALITY
  ));
}

/**
 * The photo exactly as the viewfinder framed it: the centre square of the video frame on screen.
 *
 * Not `ImageCapture.takePhoto()`. The full-sensor still it returns has a different field of view
 * from the preview — on the owner's phone a narrower one, so every line lost its start and its end
 * between framing the page and reading it. What is on screen is what is read and what is kept, and
 * the cost is resolution: a video frame is about 1080–1440 px square, where the spike measured the
 * tapped word still found 98% of the time at 1280.
 */
export function still(video: HTMLVideoElement): HTMLCanvasElement {
  const side = Math.min(video.videoWidth, video.videoHeight);
  const size = Math.min(side, LONG_EDGE);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  canvas.getContext("2d")?.drawImage(
    video, (video.videoWidth - side) / 2, (video.videoHeight - side) / 2, side, side, 0, 0, size, size
  );
  return canvas;
}

/**
 * A square cut from a photo already sent, as a JPEG: the part of a tall screenshot that was on screen
 * when Add was pressed. `top` and `size` are shares of the photo's height; the width is all of it.
 */
export async function cropSquare(photo: Blob, top: number, size: number): Promise<Blob> {
  const bitmap = await createImageBitmap(photo);
  const side = bitmap.width;
  const canvas = document.createElement("canvas");
  canvas.width = side;
  canvas.height = Math.min(side, Math.round(size * bitmap.height));
  canvas.getContext("2d")?.drawImage(bitmap, 0, -Math.round(top * bitmap.height));
  bitmap.close();
  return encodePhoto(canvas);
}
