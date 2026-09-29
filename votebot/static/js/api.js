// JSON calls to the VoteBot backend, with FastAPI's error detail surfaced as the message.

// ``signal`` (an AbortController's) cancels the call; the AbortError is passed on as it is.
async function request(method, url, body, { signal } = {}) {
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Can't reach the VoteBot server. Is it still running?");
  }
  const data = await response.json().catch(() => null);
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
  post: (url, body = {}) => request("POST", url, body),
  put: (url, body) => request("PUT", url, body),
};
