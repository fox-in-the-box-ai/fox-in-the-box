/**
 * Ollama mock — Phase 0 stub.
 *
 * Phase 1+ will register Playwright's `page.route()` interceptors against
 * the host-mapped Ollama URL (`http://host.docker.internal:11434` from inside
 * the container — but tests run from outside, so this is a webui-side probe
 * the test intercepts). Drives deterministic responses for daemon-up,
 * daemon-down, model-installed, and model-missing scenarios.
 */
import { Page } from '@playwright/test';

export type OllamaMockScenario =
  | 'daemon_down'
  | 'daemon_up_no_models'
  | 'daemon_up_with_phi4_mini'
  | 'daemon_up_with_llama31_8b';

export async function mockOllama(
  _page: Page,
  _scenario: OllamaMockScenario,
): Promise<void> {
  // Phase 1 implementation deferred — see #265.
  return;
}
