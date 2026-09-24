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
 * The best still the camera can give. `ImageCapture.takePhoto()` is the full sensor with the camera's
 * own focus, and only Chrome on Android has it; everywhere else it is the video frame on screen,
 * which is usually 1080p at most. Which is sharper on the owner's phone is still to be compared.
 */
export async function still(video: HTMLVideoElement, track: MediaStreamTrack | null): Promise<Blob | HTMLCanvasElement> {
  const Capture = (globalThis as unknown as { ImageCapture?: new (track: MediaStreamTrack) => { takePhoto(): Promise<Blob> } }).ImageCapture;
  if (Capture && track) {
    try {
      return await new Capture(track).takePhoto();
    } catch {
      /* the frame on screen is still a photo */
    }
  }
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d")?.drawImage(video, 0, 0);
  return canvas;
}
