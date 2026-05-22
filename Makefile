# Fox in the Box — developer convenience targets.
#
# The build system itself is pnpm + Docker; this Makefile is just a thin
# layer for overlay-maintenance commands per #328's recommendations.

.PHONY: validate-overlay regen-patch help

help:
	@echo "Available targets:"
	@echo "  make validate-overlay              — run the 3-check overlay sanity gate"
	@echo "                                       (submodule clean + patch series + bootstrap smoke)"
	@echo "  make regen-patch FORK=… PATCH=…    — atomically regenerate a webui/agent patch"
	@echo "                                       Example: make regen-patch FORK=webui PATCH=003-foo.patch"

# Per #328 + the v0.7.13 retrospective: run this BEFORE every commit
# that touches packages/fox-overlay/** or forks/**. Catches anchor
# drift, dirty submodule state, and stale patch series in ~2 seconds
# instead of waiting 3+ minutes for CI's Docker build to fail.
validate-overlay:
	@bash packages/fox-overlay/scripts/validate-overlay.sh

regen-patch:
	@if [ -z "$(FORK)" ] || [ -z "$(PATCH)" ]; then \
		echo "Usage: make regen-patch FORK=<agent|webui> PATCH=<name>.patch"; \
		exit 1; \
	fi
	@bash packages/fox-overlay/scripts/regen-patch.sh "$(FORK)" "$(PATCH)"
