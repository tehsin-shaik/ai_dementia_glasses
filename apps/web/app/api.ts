"use client";

export const USER_ID_HEADER = "X-MemoryCue-User-Id";
export const CAREGIVER_ID_HEADER = "X-MemoryCue-Caregiver-Id";

function identityFetch(
  input: RequestInfo | URL,
  headerName: string,
  identityId: number,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set(headerName, String(identityId));
  return fetch(input, { ...init, headers });
}

export function memoryCueFetch(
  input: RequestInfo | URL,
  userId: number | null,
  init: RequestInit = {},
): Promise<Response> {
  if (userId === null) {
    return fetch(input, init);
  }
  return identityFetch(input, USER_ID_HEADER, userId, init);
}

export function caregiverFetch(
  input: RequestInfo | URL,
  caregiverId: number,
  init: RequestInit = {},
): Promise<Response> {
  return identityFetch(input, CAREGIVER_ID_HEADER, caregiverId, init);
}
