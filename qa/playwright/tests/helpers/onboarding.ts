/**
 * Onboarding-reset race guard for smoke specs (#779, generalized from #778).
 *
 * Endpoints outside the onboarding whitelist 302-redirect to the onboarding
 * HTML page whenever the app is in onboarding state. Specs call
 * /api/setup/skip first, but a parallel spec's /test/reset landing between
 * the skip and the request re-enters onboarding and the request gets HTML
 * instead of JSON. Nightly runs with 0 retries by design, so the guard
 * lives here: re-skip immediately before each of up to 3 attempts, and
 * return as soon as the status is one the caller accepts.
 *
 * The final response is returned WITHOUT asserting — callers keep their own
 * status assertions so failure messages stay spec-specific. A genuinely
 * broken endpoint therefore fails the caller's assertion with the caller's
 * diagnostics after 3 bounded attempts (the retry absorbs at most 2
 * transient wrong-status responses; see #779 for the trade-off record).
 */
import type { APIRequestContext, APIResponse } from "@playwright/test";

const ATTEMPTS = 3;

export async function getSkippingOnboarding(
  api: APIRequestContext,
  path: string,
  okStatuses: number[] = [200],
): Promise<APIResponse> {
  let res!: APIResponse;
  for (let attempt = 0; attempt < ATTEMPTS; attempt++) {
    await api.post("/api/setup/skip");
    res = await api.get(path);
    if (okStatuses.includes(res.status())) break;
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
    res = await api.post(path, { data });
    if (okStatuses.includes(res.status())) break;
  }
  return res;
}
