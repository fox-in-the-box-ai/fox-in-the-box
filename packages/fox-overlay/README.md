# fox-overlay

Sibling package holding all Fox-in-the-Box-specific code that overlays the
virgin upstream `hermes-agent` and `hermes-webui` submodules. Lets the
submodules point at unmodified upstream tags so Fox can absorb upstream
releases weekly instead of carrying a perpetually-conflicting fork.

See `docs/architecture/upstream-migration-execution-plan.md` for the full
10-phase plan introducing this package, and the v0.6.0 epic
([#155](https://github.com/fox-in-the-box-ai/fox-in-the-box/issues/155))
for live status.

This README expands as phases 2-10 populate the tree.
