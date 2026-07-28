const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0, must-revalidate",
  Pragma: "no-cache",
  Expires: "0",
};

function mergeHeaders(defaults: HeadersInit, overrides: HeadersInit = {}) {
  const headers = new Headers(defaults);
  new Headers(overrides).forEach((value, key) => {
    headers.set(key, value);
  });
  return headers;
}

export function noStoreJson(data: unknown, init: ResponseInit = {}) {
  return Response.json(data, {
    ...init,
    headers: mergeHeaders(NO_STORE_HEADERS, init.headers),
  });
}

export const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-store, max-age=0",
  Pragma: "no-cache",
  Expires: "0",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
};
