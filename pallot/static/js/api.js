// JSON calls to the Pallot backend, with FastAPI's error detail surfaced as the message. Each
// carries the voter's choice of sources (kept in this browser), so the server uses theirs.

import { sourceChoices } from "./storage.js";

const SOURCES_HEADER = "X-Pallot-Sources";

const UNREACHABLE = "Can't reach the Pallot server. Is it still running?";

// ``signal`` (an AbortController's) cancels the call; the AbortError is passed on as it is.
async function send(method, url, body, { signal, accept } = {}) {
  try {
    return await fetch(url, {
      method,
      headers: {
        [SOURCES_HEADER]: JSON.stringify(sourceChoices()),
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(accept ? { Accept: accept } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(UNREACHABLE);
  }
}

async function readJson(response) {
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

async function request(method, url, body, options) {
  return readJson(await send(method, url, body, options));
}

// A POST answered with one JSON value per line (NDJSON), each yielded as it arrives. An error
// status throws as request() does.
async function* lines(url, body = {}, options = {}) {
  const response = await send("POST", url, body, { ...options, accept: "application/x-ndjson" });
  if (!response.ok || !response.body) {
    yield await readJson(response);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  for (;;) {
    let chunk;
    try {
      chunk = await reader.read();
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new Error(UNREACHABLE);
    }
    buffered += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
    const parts = buffered.split("\n");
    buffered = parts.pop();
    for (const part of parts) if (part.trim()) yield JSON.parse(part);
    if (chunk.done) break;
  }
  if (buffered.trim()) yield JSON.parse(buffered);
}

export const api = {
  get: (url, options) => request("GET", url, undefined, options),
  post: (url, body = {}, options) => request("POST", url, body, options),
  lines,
};
