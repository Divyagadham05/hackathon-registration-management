export default async function handler(req, res) {
  const backendOrigin = process.env.API_BACKEND_URL;
  if (!backendOrigin) {
    return res.status(503).json({
      error: "The API backend is not configured. Set API_BACKEND_URL in Vercel.",
    });
  }

  let backendUrl;
  try {
    backendUrl = new URL(backendOrigin);
    if (backendUrl.protocol !== "https:") {
      throw new Error("API_BACKEND_URL must use HTTPS.");
    }
  } catch {
    return res.status(500).json({
      error: "API_BACKEND_URL must be a valid HTTPS backend URL.",
    });
  }

  const incomingUrl = new URL(req.url, "https://vercel.local");
  backendUrl.pathname = incomingUrl.pathname;
  backendUrl.search = incomingUrl.search;

  const headers = new Headers();
  for (const name of ["accept", "content-type", "cookie", "x-csrf-token"]) {
    const value = req.headers[name];
    if (value) headers.set(name, Array.isArray(value) ? value.join(", ") : value);
  }

  let body;
  if (req.method !== "GET" && req.method !== "HEAD" && req.body !== undefined) {
    body = Buffer.isBuffer(req.body)
      ? req.body
      : typeof req.body === "string"
        ? req.body
        : JSON.stringify(req.body);
  }

  try {
    const upstream = await fetch(backendUrl, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
    });

    for (const name of ["cache-control", "content-disposition", "content-type", "location"]) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    const cookies = upstream.headers.getSetCookie?.();
    const sessionCookie = cookies?.length ? cookies : upstream.headers.get("set-cookie");
    if (sessionCookie) res.setHeader("set-cookie", sessionCookie);

    return res.status(upstream.status).send(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    console.error("API proxy request failed:", error);
    return res.status(502).json({
      error: "The application server could not be reached. Please try again later.",
    });
  }
}
