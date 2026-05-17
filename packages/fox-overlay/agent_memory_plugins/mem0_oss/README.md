# Mem0 OSS Memory Plugin

Self-hosted, privacy-first long-term memory using the open-source
[mem0ai](https://github.com/mem0ai/mem0) library.  No cloud API key or
external service needed — everything runs on your machine.

## How it works

- **LLM fact extraction** — after each conversation turn, mem0 uses an LLM
  to extract important facts, preferences, and context from the exchange.
- **Semantic search** — memories are stored in a local [Qdrant](https://qdrant.tech/)
  vector database.  Searches use embedding-based similarity so natural-language
  queries work well.
- **Automatic deduplication** — mem0 merges new facts with existing ones to
  avoid duplicate storage.
- **Built-in memory mirroring** — writes via the built-in `memory` tool are
  automatically mirrored into mem0 via `on_memory_write`, so nothing is lost
  whether you use the native tool or the mem0-specific tools.

## Setup

### 1. Install dependencies

```bash
pip install mem0ai qdrant-client
```

### 2. Configure a backend

**Zero extra config — auto-detect (recommended)**

If you already have a Hermes provider configured (OpenRouter, Anthropic, OpenAI,
or AWS Bedrock), mem0 OSS will automatically pick it up — no `MEM0_OSS_*` vars
needed.  The plugin mirrors the standard Hermes auxiliary provider priority:

```
OPENROUTER_API_KEY  →  uses OpenRouter (openrouter → openai adapter)
ANTHROPIC_API_KEY   →  uses Anthropic directly
OPENAI_API_KEY      →  uses OpenAI (+ OPENAI_BASE_URL if set)
AWS_ACCESS_KEY_ID   →  uses AWS Bedrock (boto3 reads creds automatically)
```

The first matching key wins.

**Option A — config.yaml (preferred for per-provider control)**

The plugin inherits from `auxiliary.default` if no `auxiliary.mem0_oss` block
exists, so if you've already set a default auxiliary provider for other tasks
you get mem0 OSS for free:

```yaml
# ~/.hermes/config.yaml
auxiliary:
  default:                    # inherited by mem0_oss and all other aux tasks
    provider: auto
    model: us.anthropic.claude-haiku-4-5-20251001-v1:0

  # Optional — override just for mem0_oss:
  mem0_oss:
    provider: openrouter      # or openai, anthropic, ollama, aws_bedrock, custom
    model: openai/gpt-4o-mini
    # api_key: ...            # optional — falls back to provider's standard env var
    # base_url: ...           # optional — for custom/local endpoints
```

Supported provider values: `openrouter`, `openai`, `anthropic`, `ollama`,
`lmstudio`, `aws_bedrock` (alias: `bedrock`), `custom`, `auto`.
`auto` uses the same env-var detection order as zero-config.

**Option B — AWS Bedrock**

If you already use Hermes with Bedrock, no additional config is needed.
The plugin reuses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION`.

LLM default: `us.anthropic.claude-haiku-4-5-20251001-v1:0`
Embedder default: `amazon.titan-embed-text-v2:0` (1024-dim)

**Option C — OpenAI**

```bash
# If OPENAI_API_KEY is already set, nothing more is needed.
# Override model/embedder explicitly if desired:
export MEM0_OSS_LLM_MODEL=gpt-4o-mini
export MEM0_OSS_EMBEDDER_MODEL=text-embedding-3-small
export MEM0_OSS_EMBEDDER_DIMS=1536
```

**Option D — Ollama (fully local, no API key)**

```bash
export MEM0_OSS_LLM_PROVIDER=ollama
export MEM0_OSS_LLM_MODEL=llama3.2
export MEM0_OSS_EMBEDDER_PROVIDER=ollama
export MEM0_OSS_EMBEDDER_MODEL=nomic-embed-text
export MEM0_OSS_EMBEDDER_DIMS=768
```

### 3. Activate

```yaml
# ~/.hermes/config.yaml
memory:
  provider: mem0_oss
```

Or use the interactive setup wizard:

```bash
hermes memory setup    # select "mem0_oss"
```

## Storage

| Path | Contents |
|------|----------|
| `$HERMES_HOME/mem0_oss/qdrant/` | Qdrant vector store (all memories) |
| `$HERMES_HOME/mem0_oss/history.db` | mem0 history SQLite database |

Override with `MEM0_OSS_VECTOR_STORE_PATH` and `MEM0_OSS_HISTORY_DB_PATH`.

Non-secret settings can also be persisted to `$HERMES_HOME/mem0_oss.json`
by the setup wizard (via `save_config`), or written manually — see
[All configuration options](#all-configuration-options).

## Agent tools

| Tool | Description |
|------|-------------|
| `mem0_oss_search` | Semantic search over stored memories |
| `mem0_oss_add` | Store a fact, preference, or context explicitly |

Facts are extracted and stored automatically on every conversation turn via
`sync_turn` — no explicit save call needed.

Writes via the built-in `memory` tool are also mirrored automatically into
mem0 via `on_memory_write`.  To explicitly save something mid-session, use
`mem0_oss_add` (or the built-in `memory` tool — both propagate to mem0).

## Concurrent access (WebUI + gateway)

The plugin uses embedded Qdrant which normally allows only one process at a
time.  To avoid conflicts when both the WebUI and the gateway run on the same
host, the plugin creates a fresh `Memory` instance per operation and releases
the Qdrant lock immediately after each call.  If a brief overlap occurs the
operation is skipped gracefully (logged at DEBUG, not counted as a failure)
rather than raising an error.

## All configuration options

### Environment variables

| Env var | Default | Description |
|---------|---------|-------------|
| `MEM0_OSS_LLM_PROVIDER` | auto-detected | LLM provider (`openrouter`, `openai`, `anthropic`, `ollama`, `aws_bedrock`, …) |
| `MEM0_OSS_LLM_MODEL` | provider default | LLM model id |
| `MEM0_OSS_EMBEDDER_PROVIDER` | mirrors LLM provider | Embedder provider |
| `MEM0_OSS_EMBEDDER_MODEL` | provider default | Embedder model id |
| `MEM0_OSS_EMBEDDER_DIMS` | provider default | Embedding dimensions |
| `MEM0_OSS_COLLECTION` | `hermes` | Qdrant collection name |
| `MEM0_OSS_USER_ID` | `hermes-user` | Memory namespace |
| `MEM0_OSS_TOP_K` | `10` | Default search result count |
| `MEM0_OSS_VECTOR_STORE_PATH` | `$HERMES_HOME/mem0_oss/qdrant` | On-disk Qdrant path |
| `MEM0_OSS_HISTORY_DB_PATH` | `$HERMES_HOME/mem0_oss/history.db` | SQLite history path |
| `MEM0_OSS_API_KEY` | _(auto-detected from provider env var)_ | Explicit API key for the LLM backend |
| `MEM0_OSS_OPENAI_BASE_URL` | _(none)_ | OpenAI-compatible endpoint override |

### config.yaml (auxiliary.mem0_oss / auxiliary.default)

`auxiliary.mem0_oss` keys take precedence; any key not set there falls back to
`auxiliary.default` (which is also used by compression, vision, and other aux tasks).

| Key | Description |
|-----|-------------|
| `provider` | Hermes provider name (see auto-detect order above) |
| `model` | LLM model id |
| `base_url` | Custom OpenAI-compatible endpoint |
| `api_key` | Explicit API key (takes precedence over env vars) |

### Key resolution priority

1. `MEM0_OSS_API_KEY` env var
2. `auxiliary.mem0_oss.api_key` in `config.yaml`
3. Provider's standard env var (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`,
   `OPENAI_API_KEY`, …) resolved via the Hermes provider registry
4. AWS credentials from environment (for Bedrock)

Or put non-secret settings in `$HERMES_HOME/mem0_oss.json` (keys are the
env-var names without the `MEM0_OSS_` prefix, in snake_case):

```json
{
  "llm_provider": "aws_bedrock",
  "llm_model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
  "embedder_provider": "aws_bedrock",
  "embedder_model": "amazon.titan-embed-text-v2:0",
  "embedder_dims": 1024,
  "collection": "hermes",
  "user_id": "hermes-user",
  "top_k": 10
}
```
