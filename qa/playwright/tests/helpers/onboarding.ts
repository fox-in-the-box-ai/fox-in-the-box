/**
 * Onboarding-reset race guard for smoke specs (#779, generalized from #778).
 *
 * Endpoints outside the onboarding whitelist 302-redirect to the onboarding
 * HTML page whenever the app is in onboarding state. Specs call
 * /api/setup/skip first, but a parallel spec's /test/reset landing between
 * the skip and the request re-enters onboarding and the request gets HTML
 * instead of JSON. Nightly runs with 0 retries by design, so the guard
 * lives here: re-skip before each of up to 6 attempts, and return as
 * soon as the status is one the caller accepts. Requests set
 * maxRedirects: 0 — otherwise the raced 302 is silently followed to the
 * onboarding page's 200 HTML and the retry loop never sees the race.
 *
 * Attempts are spaced with a growing backoff. The wizard specs only
 * ever /test/reset (they never skip), so each of OUR attempts both
 * re-skips and re-requests: exhausting the guard requires a fresh
 * reset to land inside every one of the six windows. The 2026-09-04/05
 * nightly failures (#809) happened because the old three back-to-back
 * attempts completed within tens of milliseconds — one reset-adjacent
 * stretch covered them all; spreading six attempts over ~6s makes that
 * interleaving practically impossible while staying bounded.
 *
 * The final response is returned WITHOUT asserting — callers keep their own
 * status assertions so failure messages stay spec-specific. A genuinely
 * broken endpoint therefore fails the caller's assertion with the caller's
 * diagnostics after 6 bounded attempts (the retry absorbs at most 5
 * transient wrong-status responses; see #779 for the trade-off record).
 */
import type { APIRequestContext, APIResponse } from '@playwright/test';

const ATTEMPTS = 6;
const BACKOFF_MS = 400;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function getSkippingOnboarding(
  api: APIRequestContext,
  path: string,
  okStatuses: number[] = [200],
): Promise<APIResponse> {
  let res!: APIResponse;
  for (let attempt = 0; attempt < ATTEMPTS; attempt++) {
    await api.post("/api/setup/skip");
    res = await api.get(path, { maxRedirects: 0 });
    if (okStatuses.includes(res.status())) break;
    if (attempt < ATTEMPTS - 1) await sleep(BACKOFF_MS * (attempt + 1));
  }
  return res;
}

export async function postSkippingOnboarding(
  api: APIRequestContext,
  path: string,
  data: unknown = {},
  okStatuses: number[] = [200],
): Promise<APIResponse> {
  let res!: APIResponse;
  for (let attempt = 0; attempt < ATTEMPTS; attempt++) {
    await api.post("/api/setup/skip");
    res = await api.post(path, { data, maxRedirects: 0 });
    if (okStatuses.includes(res.status())) break;
    if (attempt < ATTEMPTS - 1) await sleep(BACKOFF_MS * (attempt + 1));
  }
  return res;
}
