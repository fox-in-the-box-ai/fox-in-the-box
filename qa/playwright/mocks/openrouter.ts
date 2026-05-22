/**
 * OpenRouter mock — Phase 0 stub.
 *
 * Phase 1+ will register Playwright's `page.route()` interceptors against
 * https://openrouter.ai/* so wizard + chat specs can run deterministically
 * without hitting real OpenRouter. Returns canned SSE streams + key-validation
 * responses keyed off the test's intent.
 *
 * Shape established here so Phase 1 specs can import and extend.
 */
import { Page } from '@playwright/test';

export type OpenRouterMockScenario =
  | 'happy'
  | 'auth_mismatch'   // 401, drives Fox's silent failover (#303 symptom 3)
  | 'quota_exhausted' // 402, surfaces upstream error (Fox does NOT fail over)
  | 'rate_limit'      // 429, drives failover when local is ready
  | 'no_response';    // timeout

/**
 * Phase 1 entry point — register intercepts for an OpenRouter scenario.
 * Phase 0 is a no-op; the /health smoke spec doesn't talk to OpenRouter.
 */
export async function mockOpenRouter(
  _page: Page,
  _scenario: OpenRouterMockScenario,
): Promise<void> {
  // Phase 1 implementation deferred — see #265.
  return;
}
