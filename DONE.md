# DONE — fix/bedrock-imds-no-silent-auth

## What

Fox no longer treats EC2/Lightsail **IMDS instance roles** as silent Bedrock
authentication, and no longer labels Bedrock as **OAuth** in Settings → Providers.

### Root cause

1. Upstream `agent.bedrock_adapter.resolve_aws_auth_env_var` falls back to boto3
   and returns `"iam-role"` for IMDS.
2. `has_aws_credentials()` → true → provider auto-select / auth status logged in.
3. WebUI `get_providers()` treats any logged-in provider without an API-key env
   var as OAuth (`is_oauth=True`, `key_source="oauth"`) → UI copy
   “Authenticated via OAuth. No API key needed.”

On Lightsail this produces a false “authenticated” Bedrock card and then
`bedrock:InvokeModelWithResponseStream` **403** when the instance role lacks
Bedrock rights.

### Fix (fox-overlay only — no fork edits)

| Piece | Role |
|-------|------|
| `fox_overlay/aws_bedrock_auth.py` | Shared gate: ignore botocore method `iam-role` unless `HERMES_BEDROCK_ALLOW_INSTANCE_ROLE=1`; keep shared-credentials / explicit env sources |
| Agent monkey-patch `bedrock_imds.py` | Applied from `agent_plugins.register()` (gateway) |
| WebUI `webui_patches/providers.py` | Re-applies gate in WebUI process + wraps `get_providers` so Bedrock is never `is_oauth` |

Opt-in for intentional instance-role Bedrock:

```bash
HERMES_BEDROCK_ALLOW_INSTANCE_ROLE=1
```

## Tests

```bash
cd packages/fox-overlay
PYTHONPATH=. pytest tests/test_bedrock_imds_gate.py -v
```

All 8 tests passed locally.

## Follow-up: Bedrock always listable

When IMDS is blocked, Bedrock is no longer falsely `is_oauth`, and with no
API-key env var it is not `configurable` — so Settings filtered it out.

`010-bedrock-always-listable.patch` keeps `id==='bedrock'` in the providers
list and shows an AWS-credentials hint. Dogfood VPS was hotfixed the same way
in-container (`panels.js`).

- Fox AGENTS.md says Supervisor amends/pushes; this WIP commit is for review.
- User asked for a PR on `fox-in-the-box-ai/fox-in-the-box` — please push this
  branch and open/finish the PR if not already opened.
- Companion host defense remains in Vulpy (`VULPY_IMDS_LOCK` nft table) — separate repo.
- Empty botocore `method` is treated conservatively as IMDS-like (gated).
