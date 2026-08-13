# Mem0 OSS Memory Plugin

Self-hosted, privacy-first long-term memory using the open-source
[mem0ai](https://github.com/mem0ai/mem0) library. Everything runs on your
machine: fact extraction uses the chat provider you already have configured,
embeddings are computed by a bundled local model, and all data stays on disk.

For the full user-facing guide (provider matrix, troubleshooting, upgrade
recipes), see `docs/MEMORY.md` in the Fox in the Box repository.

## Architecture

- **Fact-extraction LLM = your main chat provider.** The plugin resolves the
  provider through the same surfaces Hermes chat uses
  (`resolve_provider_full` over config.yaml `model.provider` /
  `providers:` / `custom_providers:`, then the same credential chain: env
  vars with `~/.hermes/.env` preferred, then the credential pool populated
  by `hermes auth add`). If chat works, memory works — no extra key.
- **Embedder = always local.** A bundled `nomic-embed-text-v1.5` model
  (768 dimensions) is served by a llama.cpp embed-server on
  `127.0.0.1:8644` and reached through mem0's OpenAI adapter with an
  explicit base URL. Memory content never leaves the machine for embedding,
  and the vector-store dimensions stay stable for the life of the install.
- **Vector store = embedded Qdrant** (local path, no server), 768 dims.
- **Pinned LLM adapter.** mem0ai 2.0.10's OpenAI adapter prefers
  `OPENROUTER_API_KEY` from the environment over its config, which could
  silently reroute fact extraction. The plugin registers a pinned subclass
  (`_pinned_llm.PinnedOpenAILLM`) that rebuilds the client strictly from the
  resolved config. A version tripwire fails memory loudly (state `error`)
  if the installed mem0ai version ever differs from the audited `2.0.10`
  pin — the pin must be re-audited before any bump.
- **No telemetry.** mem0's built-in PostHog telemetry is disabled
  (`MEM0_TELEMETRY=False`) at every Fox-managed process boundary, including
  by this plugin at import time.

## The three states

Resolution always lands in exactly one visible state, written atomically to
`$HERMES_HOME/mem0_oss/state.json` and surfaced on `/readyz` and the boot
log (`memory: READY|OFF|ERROR — <reason>`):

| State     | Meaning                                                       | Examples of the exact reason                                                                                  |
| --------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **READY** | Memory active                                                 | `memory: READY — llm=openrouter, embedder=local:nomic-embed-text-v1.5`                                        |
| **OFF**   | Nothing misconfigured; memory unsupported or disabled here    | `disabled (MEM0_OSS_DISABLED=1)`; `memory fact-extraction doesn't support provider '<id>' …`; no provider yet |
| **ERROR** | Explicit configuration that cannot work; reason names the fix | `missing API key for provider 'openrouter' — set OPENROUTER_API_KEY … (credential pool was checked)`          |

There is no silent no-op: when memory is not READY, tools and the memory
prompt block are suppressed and the reason is visible. A failed memory
operation flips the state to `error` immediately (first failure, before the
circuit-breaker threshold) and stays visible until an operation succeeds or
the configuration actually changes.

## Activation and disable switches

Fresh installs ship with memory on by default:

```yaml
# config.yaml
memory:
  provider: mem0_oss
```

To disable: remove the `memory:` key, set `memory: provider: ""`, or export
`MEM0_OSS_DISABLED=1` (the container test mode does this automatically).

## Configuration overrides

Precedence: **computed defaults < environment variables <
`$HERMES_HOME/mem0_oss.json`** (the JSON file overrides individual keys).

| Env var                      | Default                            | Description                                                                            |
| ---------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------- |
| `MEM0_OSS_DISABLED`          | _(unset)_                          | `1` disables memory entirely (visible OFF)                                             |
| `MEM0_OSS_LLM_PROVIDER`      | main chat provider                 | Resolve this provider for fact extraction instead of the main one                      |
| `MEM0_OSS_LLM_MODEL`         | provider default                   | Fact-extraction model id                                                               |
| `MEM0_OSS_API_KEY`           | resolved like chat                 | Dedicated key for memory LLM calls                                                     |
| `MEM0_OSS_BASE_URL`          | resolved like chat                 | Dedicated endpoint for memory LLM calls (`MEM0_OSS_OPENAI_BASE_URL` is a legacy alias) |
| `MEM0_OSS_EMBEDDER_PROVIDER` | local                              | `openai` (any OpenAI-compatible endpoint) or `aws_bedrock`                             |
| `MEM0_OSS_EMBEDDER_MODEL`    | `nomic-embed-text-v1.5`            | Embedder model id                                                                      |
| `MEM0_OSS_EMBEDDER_BASE_URL` | `http://127.0.0.1:8644/v1`         | Embedder endpoint override                                                             |
| `MEM0_OSS_EMBEDDER_DIMS`     | 768                                | Embedding dimensions (flows to embedder AND vector store)                              |
| `MEM0_OSS_COLLECTION`        | `hermes`                           | Qdrant collection name                                                                 |
| `MEM0_OSS_USER_ID`           | `hermes-user`                      | Memory namespace                                                                       |
| `MEM0_OSS_TOP_K`             | `10`                               | Default search result count                                                            |
| `MEM0_OSS_VECTOR_STORE_PATH` | `$HERMES_HOME/mem0_oss/qdrant`     | On-disk Qdrant path                                                                    |
| `MEM0_OSS_HISTORY_DB_PATH`   | `$HERMES_HOME/mem0_oss/history.db` | SQLite history path                                                                    |

`$HERMES_HOME/mem0_oss.json` accepts the same keys in snake_case without
the `MEM0_OSS_` prefix (`llm_provider`, `llm_model`, `api_key`, `base_url`,
`embedder_provider`, `embedder_model`, `embedder_base_url`,
`embedder_dims`, `collection`, `user_id`, `top_k`, …). If that file exists
with embedder keys, it silently shadows the env vars — edit the file.

Credential changes (key rotation in `~/.hermes/.env`, `hermes auth add`)
take effect without a restart: the resolver watches the mtimes of
config.yaml, `.env`, and the auth store. Changes made only via shell
`export` self-heal within 10 minutes or on restart.

## Storage

| Path                               | Contents                           |
| ---------------------------------- | ---------------------------------- |
| `$HERMES_HOME/mem0_oss/qdrant/`    | Qdrant vector store (all memories) |
| `$HERMES_HOME/mem0_oss/history.db` | mem0 history SQLite database       |
| `$HERMES_HOME/mem0_oss/state.json` | Current memory state + reason      |

To reset memory completely, stop the services and delete
`$HERMES_HOME/mem0_oss/`. Nothing is ever deleted automatically.

## Agent tools

| Tool              | Description                                                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `mem0_oss_search` | Semantic search over stored memories                                                                                                   |
| `mem0_oss_add`    | Store a durable fact: preferences, environment details, decisions, corrections. Skips session events, work logs, and short-lived state |

Facts are extracted and stored automatically on every conversation turn via
`sync_turn`. Writes via the built-in `memory` tool are mirrored into mem0
via `on_memory_write`. When memory is not READY, the tools are not offered.

## Concurrent access (WebUI + gateway)

The plugin uses embedded Qdrant which normally allows only one process at a
time. To avoid conflicts when both the WebUI and the gateway run on the same
host, the plugin creates a fresh `Memory` instance per operation and releases
the Qdrant lock immediately after each call. If a brief overlap occurs the
operation is skipped gracefully (logged at DEBUG, not counted as a failure)
rather than raising an error.
