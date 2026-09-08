"use client";

export const MAX_CAPTURE_DIMENSION = 1280;

export type CaptureDimensions = {
  width: number;
  height: number;
};

export function captureDimensions(
  videoWidth: number,
  videoHeight: number,
  maxDimension = MAX_CAPTURE_DIMENSION,
): CaptureDimensions {
  if (
    !Number.isFinite(videoWidth) ||
    !Number.isFinite(videoHeight) ||
    videoWidth <= 0 ||
    videoHeight <= 0 ||
    maxDimension <= 0
  ) {
    throw new Error("The camera frame is not ready.");
  }

  const scale = Math.min(1, maxDimension / Math.max(videoWidth, videoHeight));
  return {
    width: Math.max(1, Math.round(videoWidth * scale)),
    height: Math.max(1, Math.round(videoHeight * scale)),
  };
}

export function captureVideoFrame(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  capturedAt = Date.now(),
): Promise<File> {
  const dimensions = captureDimensions(video.videoWidth, video.videoHeight);
  canvas.width = dimensions.width;
  canvas.height = dimensions.height;

  const context = canvas.getContext("2d");
  if (!context) {
    return Promise.reject(new Error("The camera frame could not be prepared."));
  }

  context.drawImage(video, 0, 0, dimensions.width, dimensions.height);
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("The camera frame could not be captured."));
          return;
        }
        resolve(
          new File([blob], `glasses-capture-${capturedAt}.jpg`, {
            type: "image/jpeg",
            lastModified: capturedAt,
          }),
        );
      },
      "image/jpeg",
      0.88,
    );
  });
}
