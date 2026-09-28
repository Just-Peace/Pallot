// JSON calls to the VoteBot backend, with FastAPI's error detail surfaced as the message.

async function request(method, url, body) {
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
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
  get: (url) => request("GET", url),
  post: (url, body = {}) => request("POST", url, body),
  put: (url, body) => request("PUT", url, body),
};
