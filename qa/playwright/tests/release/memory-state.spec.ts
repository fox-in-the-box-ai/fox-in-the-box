/**
 * Release-only — /readyz memory component.
 *
 * First spec of the `release` project (gated behind FITB_RELEASE_E2E in
 * playwright.config.ts — it never runs in ordinary smoke contexts). Asserts
 * the long-term-memory state surface exists on /readyz: the memory component
 * must be present with an ok boolean, whatever state the install is in
 * (ready / off / error are all legitimate — a MISSING component means the
 * state surface regressed). The release suite grows in later gates.
 */
import { test, expect, request } from "@playwright/test";

test.describe("Release — memory state on /readyz", () => {
  test("/readyz exposes a memory component with an ok boolean", async ({
    baseURL,
  }) => {
    const api = await request.newContext({ baseURL });
    const res = await api.get("/readyz");
    expect(res.status(), "/readyz must return 200").toBe(200);
    const body = await res.json();
    expect(body, "missing checks object").toHaveProperty("checks");
    expect(
      body.checks,
      "/readyz must include a memory component — memory state must be visible, never a silent no-op",
    ).toHaveProperty("memory");
    expect(
      typeof body.checks.memory.ok,
      "memory check ok must be boolean",
    ).toBe("boolean");
    await api.dispose();
  });
});
