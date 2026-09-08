"use client";

export const USER_ID_HEADER = "X-MemoryCue-User-Id";

export function memoryCueFetch(
  input: RequestInfo | URL,
  userId: number | null,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (userId !== null) {
    headers.set(USER_ID_HEADER, String(userId));
  }
  return fetch(input, { ...init, headers });
}
