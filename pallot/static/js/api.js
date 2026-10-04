// JSON calls to the Pallot backend, with FastAPI's error detail surfaced as the message. Each
// carries the voter's choice of sources (kept in this browser), so the server uses theirs.

import { sourceChoices } from "./storage.js";

const SOURCES_HEADER = "X-Pallot-Sources";

// ``signal`` (an AbortController's) cancels the call; the AbortError is passed on as it is.
async function request(method, url, body, { signal } = {}) {
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        [SOURCES_HEADER]: JSON.stringify(sourceChoices()),
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Can't reach the Pallot server. Is it still running?");
  }
  const data = await response.json().catch((error) => {
    if (error.name === "AbortError") throw error;
    return null;
  });
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join("; ")
      : detail || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

export const api = {
  get: (url, options) => request("GET", url, undefined, options),
  post: (url, body = {}, options) => request("POST", url, body, options),
};
