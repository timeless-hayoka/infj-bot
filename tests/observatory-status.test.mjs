import assert from "node:assert/strict";
import { test } from "node:test";
import { getPublicStatus } from "../api/status.js";

test("missing configuration is explicitly offline", async () => {
  assert.deepEqual(await getPublicStatus({}), {
    status: "offline", liveInference: false, memoryAccess: false,
  });
});

test("invalid or unsafe upstream origins fail closed", async () => {
  for (const origin of ["http://localhost:8000", "https://user:pass@example.com", "https://example.com/path", "https://example.com?x=1"]) {
    assert.equal((await getPublicStatus({ DRIFT_BACKEND_ORIGIN: origin, DRIFT_PLUGIN_TOKEN: "test-token-long-enough" })).status, "offline");
  }
});

test("configured real adapter is reachable when integration environment is supplied", async (t) => {
  if (process.env.DRIFT_STATUS_INTEGRATION !== "1") {
    t.skip("requires an actual authenticated HTTPS adapter");
    return;
  }
  const result = await getPublicStatus(process.env);
  assert.deepEqual(result, { status: "ready", liveInference: false, memoryAccess: false });
  const invalid = await getPublicStatus({ ...process.env, DRIFT_PLUGIN_TOKEN: "incorrect-token-long-enough" });
  assert.equal(invalid.status, "offline");
});
