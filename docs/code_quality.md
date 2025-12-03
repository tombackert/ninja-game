# Code Quality & Testing Strategy

**Status:** Active
**Philosophy:** "Keep It Simple, Strict, and Fast."

We prioritize a minimal set of high-performance tools to enforce strict code quality standards with zero configuration headaches.

Run: `./tools/check_quality.sh`

---

## 1. The Tool Stack

We use a consolidated toolchain to minimize dependencies and maximize speed.

| Category          | Tool       | Role                                   | Configuration                           |
| :---              | :---       | :---                                   | :---                                    |
| **Formatting**    | **Black**  | Formatting                             | `pyproject.toml`                        |
| **Linting**       | **Ruff**   | Linting. Replaces Flake8/Isort         | `pyproject.toml` (Rules: E, F)          |
| **Type Checking** | **Mypy**   | Static type checker                    | `pyproject.toml` (Strict on `scripts/`) |
| **Testing**       | **Pytest** | Unit and integration testing framework | `pyproject.toml`                        |

### Configuration Details
- **Line Length:** 120 characters
- **Python Version:** 3.12+
- **Ruff Rules:**
    - `E`: Standard Pycodestyle errors
    - `F`: Pyflakes (unused imports, undefined names, etc.)
    - `E203`: Ignored (Whitespace before colon) for Black compatibility

---

## 2. Workflows

### A. Local Development (Manual)
Run the consolidated check script before pushing. This runs the exact same steps as the CI server.

```bash
./tools/check_quality.sh
```

### B. Pre-Commit Hooks (Automatic)
We use `pre-commit` to prevent bad commits locally.

**Setup:**
```bash
pip install pre-commit
pre-commit install
```

**Checks:**
- `ruff` (Fix mode)
- `black`
- `mypy` (Targeting `scripts/`)
- `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`

### C. Continuous Integration (GitHub Actions)
Every Push and Pull Request triggers the `CI` workflow (`.github/workflows/ci.yml`).

**Steps:**
1.  **Lint:** `ruff check .`
2.  **Format Check:** `black --check .`
3.  **Type Check:** `mypy scripts`
4.  **Test:** `pytest -q`

**Policy:**
- The main branch is protected
- CI must pass (green) before merging
- No "lenient" checks; warnings are treated as errors where possible

---

## 3. Testing Standards

- **Unit Tests:** Located in `tests/`. Should be fast and mock external dependencies (like Pygame display)
- **Headless Mode:** Tests set `SDL_VIDEODRIVER=dummy` to run without a display
- **Coverage:** Focus on core logic in `scripts/` (Entities, Physics, AI, Networking)
