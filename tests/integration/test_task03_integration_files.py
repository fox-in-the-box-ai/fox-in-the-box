"""Validate Task 03 integration artifacts (Dockerfile, supervisord, entrypoint).

Maps to acceptance criteria 1 and structural checks; full container AC2–AC6 need
`docker build` / `docker run` (see docs/tasks/03-dockerfile.md Test Commands).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


class TestDockerfile(unittest.TestCase):
    def setUp(self) -> None:
        self.df = _read("packages/integration/Dockerfile")

    def test_ac1_base_and_pinned_qdrant(self) -> None:
        self.assertIn("FROM python:3.11-slim", self.df)
        self.assertRegex(self.df, r"ARG\s+QDRANT_VERSION=v1\.9\.4")
        self.assertNotRegex(
            self.df,
            re.compile(
                r"github\.com/qdrant/qdrant/releases/download/latest",
                re.IGNORECASE,
            ),
        )

    def test_non_root_user_named_foxinthebox(self) -> None:
        self.assertRegex(self.df, r"useradd\s+.*\sfoxinthebox")
        self.assertNotIn("fox-in-the-box", self.df)

    def test_expose_and_entrypoint(self) -> None:
        self.assertIn("EXPOSE 8787 6333", self.df)
        self.assertIn('ENTRYPOINT ["/app/entrypoint.sh"]', self.df)

    def test_supervisor_and_paths_copied(self) -> None:
        self.assertIn("pip install --no-cache-dir supervisor", self.df)
        self.assertIn("COPY forks/hermes-agent", self.df)
        self.assertIn("COPY forks/hermes-webui", self.df)
        self.assertIn("COPY packages/integration/supervisord.conf", self.df)
        self.assertIn("COPY packages/integration/entrypoint.sh", self.df)
        self.assertIn("COPY packages/integration/scripts/", self.df)

    def test_within_container_marker_for_webui(self) -> None:
        self.assertIn("/.within_container", self.df)


class TestSupervisordConf(unittest.TestCase):
    def setUp(self) -> None:
        self.ini = _read("packages/integration/supervisord.conf")

    def test_four_programs_defined(self) -> None:
        for name in (
            "program:tailscaled",
            "program:qdrant",
            "program:hermes-gateway",
            "program:hermes-webui",
        ):
            with self.subTest(name=name):
                self.assertIn(f"[{name}]", self.ini)

    def test_tailscaled_runs_as_root(self) -> None:
        tail = self.ini.split("[program:tailscaled]", 1)[1].split("[", 1)[0]
        self.assertIn("user=root", tail)

    def test_qdrant_and_apps_run_as_foxinthebox(self) -> None:
        for label in ("[program:qdrant]", "[program:hermes-gateway]", "[program:hermes-webui]"):
            block = self.ini.split(label, 1)[1].split("[", 1)[0]
            with self.subTest(label=label):
                self.assertIn("user=foxinthebox", block)

    def test_data_paths(self) -> None:
        self.assertIn("command=/app/qdrant/qdrant --config-path /data/config/qdrant.yaml", self.ini)
        self.assertIn("tailscaled --state=/data/data/tailscale/tailscaled.state", self.ini)
        self.assertIn('PYTHONPATH="/data/apps/hermes-agent"', self.ini)
        self.assertIn('PYTHONPATH="/data/apps/hermes-webui"', self.ini)

    def test_webui_binds_all_interfaces_in_container(self) -> None:
        self.assertIn('HERMES_WEBUI_HOST="0.0.0.0"', self.ini)
        self.assertIn('HERMES_WEBUI_AGENT_DIR="/data/apps/hermes-agent"', self.ini)

    def test_supervisord_socket_not_on_data_volume(self) -> None:
        """AF_UNIX on bind-mounted /data fails on Docker Desktop (macOS/Windows)."""
        self.assertIn("pidfile=/run/fitb/supervisord.pid", self.ini)
        self.assertIn("file=/run/fitb/supervisor.sock", self.ini)
        self.assertIn("serverurl=unix:///run/fitb/supervisor.sock", self.ini)
        self.assertNotIn("file=/data/run/supervisor.sock", self.ini)


class TestEntrypoint(unittest.TestCase):
    def setUp(self) -> None:
        self.sh = _read("packages/integration/entrypoint.sh")

    def test_symlink_hermes_and_supervisord_exec(self) -> None:
        self.assertIn("set -euo pipefail", self.sh)
        self.assertIn("/data/apps", self.sh)
        self.assertIn("_link_hermes_app", self.sh)
        self.assertIn("/app/hermes-agent", self.sh)
        self.assertIn("mkdir -p /run/fitb", self.sh)
        self.assertIn("exec /usr/local/bin/supervisord", self.sh)

    def test_dev_mode_pip_installs_webui_when_present(self) -> None:
        self.assertIn("requirements.txt", self.sh)
        self.assertIn("hermes-webui", self.sh)


if __name__ == "__main__":
    unittest.main()
