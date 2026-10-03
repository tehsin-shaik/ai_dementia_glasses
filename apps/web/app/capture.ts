"use client";

import { captureVideoFrame } from "./camera";

export type CaptureSourceName = "browser_camera" | "iphone_camera" | "meta_glasses" | "uploaded_image" | "other";

export type Capture = {
  image: File;
  capturedAt: Date;
  source: CaptureSourceName;
  latitude?: number;
  longitude?: number;
};

export type CaptureSource = {
  source: CaptureSourceName;
  capture: () => Promise<Capture>;
};

export function browserCameraSource(video: HTMLVideoElement, canvas: HTMLCanvasElement): CaptureSource {
  return {
    source: "browser_camera",
    async capture() {
      const capturedAt = new Date();
      const image = await captureVideoFrame(video, canvas, capturedAt.getTime());
      return { image, capturedAt, source: "browser_camera" };
    },
  };
}

export function localTimestamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}:${pad(date.getSeconds())}`;
}

export function observationFormData(capture: Capture): FormData {
  const formData = new FormData();
  formData.append("image", capture.image);
  formData.append("timestamp", localTimestamp(capture.capturedAt));
  formData.append("source", capture.source);
  formData.append("analyze", "false");
  if (capture.latitude !== undefined && capture.longitude !== undefined) {
    formData.append("latitude", String(capture.latitude));
    formData.append("longitude", String(capture.longitude));
  }
  return formData;
}
