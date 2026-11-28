// Only expose a fixed health result. Never proxy arbitrary URLs or memory data.
const result = (status) => ({ status, liveInference: false, memoryAccess: false });

export async function getPublicStatus(env = process.env) {
  const token = env.DRIFT_PLUGIN_TOKEN;
  if (!token || token.length < 16 || !env.DRIFT_BACKEND_ORIGIN) return result("offline");
  try {
    const origin = new URL(env.DRIFT_BACKEND_ORIGIN);
    if (origin.protocol !== "https:" || origin.username || origin.password ||
        origin.pathname !== "/" || origin.search || origin.hash) return result("offline");
    const response = await fetch(new URL("/health", origin), {
      method: "GET",
      headers: { Authorization: "Bearer " + token, Accept: "application/json" },
      redirect: "error",
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) return result("offline");
    const body = await response.json();
    return result(body.status === "ready" && body.adapter === "drift-readonly-v1" ? "ready" : "offline");
  } catch {
    return result("offline");
  }
}

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return res.status(405).json({ error: "Method not allowed" });
  }
  const status = await getPublicStatus();
  return res.status(status.status === "ready" ? 200 : 503).json(status);
}
