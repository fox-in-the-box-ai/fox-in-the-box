# Long-Term Memory

Fox in the Box ships with long-term memory enabled by default on fresh
installs (v0.7.60+). Facts from your conversations are extracted with the
chat provider you already use and stored **locally** — a self-hosted
[mem0](https://github.com/mem0ai/mem0) store with an embedded Qdrant vector
database under the instance data volume. Embeddings are computed entirely
on-device by a bundled local model (`nomic-embed-text-v1.5` served by
llama.cpp on `127.0.0.1:8644`), so no extra API key is needed and memory
content never leaves the machine for embedding.

Plugin-level reference (env vars, file layout, tools):
`packages/fox-overlay/agent_memory_plugins/mem0_oss/README.md`.

## The three states

Memory is never a silent no-op. It is always in exactly one visible state:

| State     | What it means                                                               | Where you see it                                                                                                                      |
| --------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **READY** | Memory active                                                               | Boot log `memory: READY — llm=<provider>, embedder=local:nomic-embed-text-v1.5`; Settings card available; `/readyz` memory `ok: true` |
| **OFF**   | Nothing is misconfigured — memory is unsupported or disabled for this setup | Boot log `memory: OFF — <reason>`; `/readyz` memory `ok: true` with the reason as detail                                              |
| **ERROR** | An explicit configuration that cannot work; the reason names the exact fix  | Boot log `memory: ERROR — <reason>`; `/readyz` memory `ok: false` with the reason                                                     |

The state lives in `$HERMES_HOME/mem0_oss/state.json`
(`/data/data/hermes/mem0_oss/state.json` in the container) and is written
at boot (preflight), on every availability evaluation, and on memory
operation failures — a failed memory operation is visible immediately, from
the first failure.

### Disable switches

```yaml
# config.yaml — remove the key or blank the provider:
memory:
  provider: ""
```

or export `MEM0_OSS_DISABLED=1`. Either produces a visible OFF with the
reason `disabled (MEM0_OSS_DISABLED=1)` (env switch) — never a silent gap.

## Supported providers

Memory mirrors your chat configuration exactly. Fact extraction resolves the
provider the same way chat does, and credentials the same way chat does:
env vars (with `~/.hermes/.env` preferred over stale shell exports), then
the credential pool (`hermes auth add <provider>`).

| Your chat setup                                                                                               | Memory behavior                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **OpenRouter** (key or `hermes auth add openrouter` pool-only)                                                | READY. Works fully offline of the models.dev catalog                                                                                                              |
| Bare `provider: openai` (no `providers.openai` entry)                                                         | Routes through OpenRouter with the OpenRouter key — exactly like chat. For direct OpenAI use `provider: openai-api`                                               |
| **Direct OpenAI** (`provider: openai-api` or `providers.openai`)                                              | READY with `OPENAI_API_KEY` @ api.openai.com. Immune to a stray exported `OPENROUTER_API_KEY`                                                                     |
| **Anthropic** (`anthropic` / `claude` / `claude-code`)                                                        | READY with `ANTHROPIC_API_KEY`                                                                                                                                    |
| **AWS Bedrock**                                                                                               | READY via the boto3 default credential chain                                                                                                                      |
| **Local family**: Ollama, vLLM, llama.cpp, LM Studio, `custom`                                                | READY against `model.base_url` (or `OLLAMA_BASE_URL` / LM Studio defaults); no key needed                                                                         |
| `providers:` / `custom_providers:` entries (incl. keyless)                                                    | READY with the entry's endpoint and key (keyless entries are supported, like chat)                                                                                |
| Built-in API-key long tail (DeepSeek, Groq, Z.AI, Gemini, azure-foundry openai-mode, kimi, kilo, opencode, …) | READY with the provider's key + endpoint (kimi/kilo/opencode pool credentials are bridged to their pool ids automatically)                                        |
| **OAuth-based** (OpenAI Codex, Nous, xAI OAuth, Qwen OAuth, MiniMax OAuth), GitHub Copilot, MoA               | OFF (visible) — no static API key / OpenAI-compatible endpoint. Override with `MEM0_OSS_LLM_PROVIDER` + `MEM0_OSS_API_KEY` to use a different provider for memory |

Notes on detection: with no `model.provider` configured, memory probes
credentials in the same order chat's auto-detection does. A **lone
`OPENAI_API_KEY` is treated as an OpenRouter credential**, exactly like
chat — direct OpenAI is config-explicit only (`provider: openai-api`).

### Caveat rows

| Setup                                                                                  | Caveat                                                                                                                                                         |
| -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ANTHROPIC_BASE_URL` proxy                                                             | Chat honors it; memory pins api.anthropic.com. Behind an Anthropic proxy, set `MEM0_OSS_BASE_URL`                                                              |
| Anthropic OAuth-token-only (`ANTHROPIC_TOKEN` / `CLAUDE_CODE_OAUTH_TOKEN`, no API key) | Resolves, but the bearer token fails at call time with a visible 401. Fix: set `ANTHROPIC_API_KEY` or a memory-specific override                               |
| `kimi-for-coding` (`/coding` endpoint)                                                 | The endpoint speaks Anthropic-style messages despite its OpenAI-style registration — memory's chat-completions calls fail at operation time, visibly           |
| Azure Foundry in **anthropic** api_mode                                                | Same class: operation-time visible failure. Openai-mode Azure Foundry works with `AZURE_FOUNDRY_API_KEY` + `AZURE_FOUNDRY_BASE_URL` — the same pair chat needs |
| kimi / Z.AI regional (CN) endpoints                                                    | Memory uses the default endpoint; a regional key 401s visibly. Fix: `MEM0_OSS_BASE_URL` (or `mem0_oss.json` `base_url`)                                        |

### Credential changes without restart

Key rotation in `~/.hermes/.env` and `hermes auth add <provider>` take
effect without restarting: the resolver watches the modification times of
config.yaml, `.env`, and the auth store (which also holds the credential
pool). Changes made only through a shell `export` self-heal within 10
minutes or on restart. Custom providers use the `custom:<name>` credential
convention, and the kimi/opencode/kilo pool ids are bridged automatically.

## models.dev catalog troubleshooting

The flagship providers (OpenRouter, Anthropic, direct OpenAI, openai-mode
Azure Foundry, Bedrock, local family) resolve **without** the models.dev
catalog. Only the built-in long tail needs it, and the error tells you which
situation you are in:

- _"provider '<id>' needs the models.dev catalog, which is unreachable and
  not cached"_ — a network problem. Check connectivity, retry, or set
  `MEM0_OSS_LLM_PROVIDER` / `MEM0_OSS_API_KEY` / `MEM0_OSS_BASE_URL`.
- _"provider '<id>' has no known endpoint / API key variable"_ — the
  catalog is healthy but does not carry this id. Define the provider under
  `providers:` / `custom_providers:` or use the `MEM0_OSS_*` overrides.

Worst case on a cold, cache-less, catalog-unreachable boot, resolution can
stall once for up to 15 seconds per 10-minute window; the flagship rows
never hit this.

## Upgrading from a remote embedder (continuity recipe)

If you previously enabled memory with a remote embedder (OpenAI
`text-embedding-3-small` 1536-dim, or Bedrock Titan 1024-dim), the new
local 768-dim default does not match your existing store. Memory reports an
explicit error naming both dimension counts. Two options — nothing is
deleted automatically:

1. **Keep your store** — restore the previous embedder settings. If
   `mem0_oss.json` exists under your Hermes data directory
   (`/data/data/hermes/mem0_oss.json` in the container,
   `$HERMES_HOME/mem0_oss.json` on bare metal) with embedder keys, edit
   **that file** (it silently shadows env vars). Otherwise:

   ```bash
   export MEM0_OSS_EMBEDDER_PROVIDER=openai
   export MEM0_OSS_EMBEDDER_MODEL=text-embedding-3-small
   export MEM0_OSS_EMBEDDER_DIMS=1536
   # Bedrock equivalents: aws_bedrock / amazon.titan-embed-text-v2:0 / 1024
   ```

   Explicit dims flow to both the embedder and the vector store, keeping the
   collection consistent.

2. **Start fresh** — stop the services and delete the
   `$HERMES_HOME/mem0_oss/` data directory. The collection is recreated at
   768 dims on the next memory operation.

## embed-server troubleshooting

| Symptom                                                                                               | Likely cause                                                                                                                                             | Fix                                                                                                                                                                                                                                                                                                                                                                         |
| ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Memory reports an embed-server error" / `supervisorctl status` shows `embed-server` STOPPED or FATAL | Embedding model missing or hash-mismatched at install time — the supervisord conf was written with `autostart=false` (or the unit exhausted its retries) | Check the log at `${data}/logs/embed-server.err` (container: `/data/logs/embed-server.err`; deb install: `/opt/foxinthebox/.foxinthebox/logs/embed-server.err`). Re-run the install/upgrade so `_install_embed_model` retries the download (every postinst re-run retries and flips `autostart` back to true once the model lands), then `supervisorctl start embed-server` |

A **sleeping** embed-server is healthy: the unit unloads the model after
120 s idle (`--sleep-idle-seconds`) and wakes on the next request. Memory's
health probe treats any HTTP response as alive; only a dead port
(connection refused / timeout) is an error.

**RAM profile:** ~95 MB loaded at boot until the idle unload, then ~50 MB
resident; ~150–300 MB transient while embedding. This applies even when
memory is off (the unit is part of the base install); disable it with
`supervisorctl stop embed-server` if you never use memory.

## Rollback / downgrade

- **Container rollback:** a fresh v0.7.60 container writes
  `memory: provider: mem0_oss` into the persisted config volume. Rolling
  that container back to `:v0.7.59` requires **removing the `memory:` key
  from `/data/config/hermes.yaml`** first — the older image's memory plugin
  predates the fail-loud rework.
- **Debian/apt downgrade to 0.7.59:** remove the `memory: provider:` line
  from hermes.yaml first (or purge the Fox venv). The Fox venv persists
  across apt downgrades and pip never uninstalls, so the older release's
  plugin would otherwise run against the newer installed dependencies.

## Telemetry

mem0's built-in PostHog telemetry is disabled (`MEM0_TELEMETRY=False`) at
every Fox-managed process boundary: the plugin sets it at import, and the
container image, supervisord units, and entrypoint all export it. No memory
content or usage events leave the machine; the only network traffic memory
adds is the fact-extraction call to the chat provider you already use.

**Residual:** if you separately invoke the upstream `mem0` backend from a
bare-metal shell outside Fox-managed processes, export
`MEM0_TELEMETRY=False` in that shell too.

## Multilingual note

The bundled `nomic-embed-text-v1.5` embedder is trained primarily on
English. Memory works with any language your chat provider understands, but
semantic recall quality for heavily non-English content may be lower; if
that matters, override the embedder (see the continuity recipe above) with
a multilingual model served at any OpenAI-compatible endpoint.
