#!/bin/bash
# Detect upstream rename/delete of any file referenced in .fox-removals.
#
# Runs as a CI gate before the Docker build (wired in Phase 8). Failure
# means the submodule pin needs to be rolled back to the previous tag
# and the overlay/migration plan updated for the upstream restructure.
#
# Phase 1: no-op stub returning 0. Phase 8 makes it real.

exit 0
