# Contributing to Fox in the Box

Thank you for your interest in contributing to Fox in the Box! We welcome contributions from everyone.

## Development Workflow

1. **Read the docs**: Before starting work, read:
   - [REQUIREMENTS.md](REQUIREMENTS.md) - Project requirements and architecture
   - [AGENTS.md](AGENTS.md) - Instructions for AI agents implementing features
   - [ROADMAP.md](ROADMAP.md) - Project roadmap

2. **Check for existing issues**: Look for existing issues or create a new one describing what you plan to work on.

3. **Create a branch**: Use descriptive branch names like `feature/add-new-tool` or `fix/docker-build-error`.

4. **Write tests**: All new features must include tests. See the testing standards in [AGENTS.md](AGENTS.md).

5. **Submit a Pull Request**: Once your work is complete, submit a PR with:
   - Description of changes
   - Link to related issue
   - Screenshots (if UI changes)
   - Test results

## Code Style

- **Python**: Follow PEP 8 guidelines
- **JavaScript**: Use ES2020+ features, no TypeScript in this project
- **Shell scripts**: Use `set -euo pipefail` at the start, define functions for reusable logic
- **Docker**: Multi-stage builds when beneficial, otherwise keep simple

## Commit Messages

Use conventional commit format:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `test:` for adding or updating tests
- `chore:` for maintenance tasks

Example: `feat: add Docker build workflow for CI/CD`

## Questions?

Feel free to open an issue or join discussions in the project.
