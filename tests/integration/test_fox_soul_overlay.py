"""Validate the Fox SOUL.md overlay (post-Phase-8 agent-side override).

The agent submodule (`forks/hermes-agent`) was re-pointed at virgin upstream in
Phase 8 ATOMIC (#237), so SOUL.md can no longer be patched in-fork. Fox now
ships its persona via `packages/fox-overlay/agent_overlay/SOUL.md`, which the
Dockerfile copies over `/app/hermes-agent/docker/SOUL.md` at build time. The
upstream entrypoint then seeds `$HERMES_HOME/SOUL.md` from that path on first
run.

These tests are pure-static (no docker build) — they verify the artifacts and
wiring exist. A full container-level assertion would require building and
running the image (see qa/ smoke checklist).
"""
from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOUL_PATH = REPO_ROOT / "packages/fox-overlay/agent_overlay/SOUL.md"
DOCKERFILE = REPO_ROOT / "packages/integration/Dockerfile"
MANIFEST = REPO_ROOT / "packages/fox-overlay/MANIFEST.toml"


class TestSoulOverlayArtifact(unittest.TestCase):
    """The SOUL.md file itself must exist and contain the Fox persona."""

    def test_soul_file_exists(self) -> None:
        self.assertTrue(
            SOUL_PATH.is_file(),
            f"missing Fox SOUL.md at {SOUL_PATH.relative_to(REPO_ROOT)}",
        )

    def test_soul_identifies_as_fox(self) -> None:
        text = SOUL_PATH.read_text(encoding="utf-8")
        # Identity must be Fox / Fox in the Box — this is the load-bearing line.
        self.assertRegex(text, r"\bFox\b")
        self.assertRegex(text, r"Fox in the Box")

    def test_soul_has_persona_header(self) -> None:
        text = SOUL_PATH.read_text(encoding="utf-8")
        # Matches the upstream convention (`# Hermes Agent Persona`) so the
        # file is recognised as a proper persona document.
        self.assertRegex(text, r"(?m)^#\s+Hermes Agent Persona")

    def test_soul_is_not_empty_or_stub(self) -> None:
        text = SOUL_PATH.read_text(encoding="utf-8").strip()
        # 200 chars is a generous lower bound — guards against accidental
        # truncation or a stray `echo > SOUL.md` wiping the file.
        self.assertGreater(
            len(text), 200, "SOUL.md is suspiciously short — likely truncated"
        )


class TestDockerfileWiring(unittest.TestCase):
    """The Dockerfile must wire the overlay copy correctly."""

    def setUp(self) -> None:
        self.df = DOCKERFILE.read_text(encoding="utf-8")

    def test_dockerfile_copies_soul_over_upstream(self) -> None:
        # The cp command (inside a RUN block) overwrites the upstream file.
        self.assertIn(
            "cp /app/fox-overlay/agent_overlay/SOUL.md /app/hermes-agent/docker/SOUL.md",
            self.df,
            "Dockerfile is missing the SOUL.md overlay cp step",
        )

    def test_dockerfile_chowns_soul_to_foxinthebox(self) -> None:
        # Without chown the file ends up root-owned and unreadable by the
        # foxinthebox runtime user. Bug-bait — fail loudly if absent.
        self.assertIn(
            "chown foxinthebox:foxinthebox /app/hermes-agent/docker/SOUL.md",
            self.df,
            "Dockerfile must chown the overlaid SOUL.md to foxinthebox",
        )

    def test_dockerfile_respects_disable_agent_overlay_escape_hatch(self) -> None:
        # Consistent with the existing agent-side overlay short-circuits
        # (mem0_oss copy, fox_overlay register hook). Lets QA/CI build a
        # virgin-upstream image without the Fox persona.
        block = self._extract_soul_run_block()
        self.assertIn('FITB_DISABLE_AGENT_OVERLAY', block,
                      "SOUL.md overlay RUN must honour FITB_DISABLE_AGENT_OVERLAY=1")

    def test_dockerfile_fails_fast_if_overlay_source_missing(self) -> None:
        # Defensive: if fox-overlay COPY regresses and agent_overlay/ disappears,
        # the build must fail at this step (not silently ship upstream persona).
        block = self._extract_soul_run_block()
        self.assertRegex(
            block,
            r"if \[ ! -f /app/fox-overlay/agent_overlay/SOUL\.md \]",
            "SOUL.md overlay RUN must guard against missing source file",
        )

    def test_dockerfile_fails_fast_if_upstream_layout_changed(self) -> None:
        # If upstream moves docker/SOUL.md, our overwrite would create a stray
        # file in a non-existent directory. Phase 9 upstream-watch should
        # catch this earlier, but a hard build-time check is the safety net.
        block = self._extract_soul_run_block()
        self.assertRegex(
            block,
            r"if \[ ! -d /app/hermes-agent/docker \]",
            "SOUL.md overlay RUN must guard against upstream layout change",
        )

    def test_dockerfile_overlay_runs_after_fox_overlay_copy(self) -> None:
        # The overlay COPY must precede the cp (otherwise the source isn't
        # there yet). Verify ordering by index of marker strings.
        copy_idx = self.df.index("COPY packages/fox-overlay /app/fox-overlay")
        cp_idx = self.df.index(
            "cp /app/fox-overlay/agent_overlay/SOUL.md /app/hermes-agent/docker/SOUL.md"
        )
        self.assertLess(
            copy_idx, cp_idx,
            "fox-overlay COPY must precede the SOUL.md cp step",
        )

    def _extract_soul_run_block(self) -> str:
        """Return the multi-line RUN that performs the SOUL.md overlay."""
        marker = "[fox-soul]"
        self.assertIn(marker, self.df,
                      "SOUL.md overlay RUN block marker not found")
        # Grab a generous window around the marker (RUN blocks are <50 lines).
        idx = self.df.index(marker)
        start = self.df.rfind("RUN ", 0, idx)
        end = self.df.find("\n\n", idx)
        if end == -1:
            end = len(self.df)
        return self.df[start:end]


class TestManifestRegistration(unittest.TestCase):
    """MANIFEST.toml is the single source of truth for what fox-overlay ships."""

    def test_manifest_lists_soul_md(self) -> None:
        data = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
        static = data.get("static", {})
        self.assertIn(
            "agent_overlay/SOUL.md", static,
            "MANIFEST.toml [static] must register agent_overlay/SOUL.md",
        )
        self.assertEqual(
            static["agent_overlay/SOUL.md"], "fox-only",
            "agent_overlay/SOUL.md classification must be 'fox-only' "
            "(it replaces upstream content, not adds alongside)",
        )


if __name__ == "__main__":
    unittest.main()
