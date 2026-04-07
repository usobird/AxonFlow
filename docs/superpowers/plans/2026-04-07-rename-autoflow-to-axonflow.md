# AxonFlow → AxonFlow Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the project from AxonFlow to AxonFlow — package name, class names, CLI entry point, config files, docs, and all import paths.

**Architecture:** Pure refactor — no logic changes. We rename in three layers: (1) the Python package directory `src/axonflow/` → `src/axonflow/`, (2) all import statements and class names inside source files, (3) config/docs/tooling that reference the old name. Tests must all pass at the end.

**Tech Stack:** Python 3.11+, hatchling (build), pytest, sed/shell for bulk renames

---

## Rename Map

| Old | New |
|-----|-----|
| `src/axonflow/` | `src/axonflow/` |
| `from axonflow.` | `from axonflow.` |
| `import axonflow` | `import axonflow` |
| `"axonflow.` (strings) | `"axonflow.` |
| `class AxonFlowEngine` | `class AxonFlowEngine` |
| `class AxonFlowConfig` | `class AxonFlowConfig` |
| `AxonFlow` (display strings) | `AxonFlow` |
| `axonflow` (CLI command) | `axonflow` |
| `config/axonflow.yaml` | `config/axonflow.yaml` |
| `REDIS_KEY_PREFIX = "axonflow"` | `REDIS_KEY_PREFIX = "axonflow"` |
| `load_global_config(path="config/axonflow.yaml")` | `load_global_config(path="config/axonflow.yaml")` |
| `pyproject.toml` name/entry/package | updated to axonflow |
| docker-compose service name | axonflow |

---

## Task 1: Rename the Python package directory

**Files:**
- Rename: `src/axonflow/` → `src/axonflow/`

This is a `git mv` — it preserves history.

- [ ] **Step 1: Run git mv to rename the directory**

```bash
git mv src/axonflow src/axonflow
```

- [ ] **Step 2: Verify the move**

```bash
ls src/axonflow/
```

Expected: shows `__init__.py`, `engine.py`, `core/`, `config/`, `llm/`, `tools/`, `memory/`, `messaging/`, `observability/`, `cli/`, `security/`, `agents/`

- [ ] **Step 3: Verify git status shows the renames**

```bash
git status --short | head -30
```

Expected: Many lines starting with `R  src/axonflow/... -> src/axonflow/...`

- [ ] **Step 4: Do NOT commit yet** — imports are all broken; commit after Task 2

---

## Task 2: Update all Python import statements

**Files:** All `.py` files in `src/axonflow/` and `tests/`

- [ ] **Step 1: Replace all `from axonflow.` with `from axonflow.` in source**

```bash
find src/axonflow -name "*.py" | xargs sed -i '' 's/from axonflow\./from axonflow./g'
```

- [ ] **Step 2: Replace all `import axonflow` with `import axonflow` in source**

```bash
find src/axonflow -name "*.py" | xargs sed -i '' 's/import axonflow$/import axonflow/g'
```

- [ ] **Step 3: Replace all `from axonflow.` in tests**

```bash
find tests -name "*.py" | xargs sed -i '' 's/from axonflow\./from axonflow./g'
```

- [ ] **Step 4: Replace all `import axonflow` in tests**

```bash
find tests -name "*.py" | xargs sed -i '' 's/import axonflow$/import axonflow/g'
```

- [ ] **Step 5: Replace string literals `"axonflow.` (used in class_path strings)**

```bash
find src/axonflow tests -name "*.py" | xargs sed -i '' 's/"axonflow\./"axonflow./g'
```

- [ ] **Step 6: Verify no remaining `axonflow` references in Python files (excluding __pycache__)**

```bash
grep -r "axonflow" src/axonflow tests --include="*.py" | grep -v "__pycache__"
```

Expected: Only legitimate references remain (e.g., `REDIS_KEY_PREFIX = "axonflow"` in defaults.py, display strings like `"AxonFlow"` — those are handled in Task 4).

- [ ] **Step 7: Verify import resolution works**

```bash
cd /Users/limingyang3/Documents/AxonFlow && python -c "from axonflow.engine import AxonFlowEngine" 2>&1 || python -c "from axonflow.config.models import AxonFlowConfig"
```

Note: This will fail because `AxonFlowEngine` and `AxonFlowConfig` class names haven't been renamed yet (Task 3). But `ModuleNotFoundError` should NOT appear — only `ImportError: cannot import name 'AxonFlowEngine'` is acceptable at this stage.

- [ ] **Step 8: Do NOT commit yet** — continue to Task 3

---

## Task 3: Rename AxonFlowEngine and AxonFlowConfig class names

**Files:**
- Modify: `src/axonflow/engine.py` — `AxonFlowEngine` → `AxonFlowEngine`
- Modify: `src/axonflow/config/models.py` — `AxonFlowConfig` → `AxonFlowConfig`
- Modify: `src/axonflow/config/loader.py` — all `AxonFlowConfig` references
- Modify: `src/axonflow/cli/app.py` — all `AxonFlowEngine` references

- [ ] **Step 1: Rename AxonFlowEngine in engine.py**

```bash
sed -i '' 's/AxonFlowEngine/AxonFlowEngine/g' src/axonflow/engine.py
```

- [ ] **Step 2: Rename AxonFlowConfig in models.py**

```bash
sed -i '' 's/AxonFlowConfig/AxonFlowConfig/g' src/axonflow/config/models.py
```

- [ ] **Step 3: Rename AxonFlowConfig in loader.py**

```bash
sed -i '' 's/AxonFlowConfig/AxonFlowConfig/g' src/axonflow/config/loader.py
```

- [ ] **Step 4: Rename AxonFlowEngine in cli/app.py**

```bash
sed -i '' 's/AxonFlowEngine/AxonFlowEngine/g' src/axonflow/cli/app.py
```

- [ ] **Step 5: Verify no AxonFlow class names remain in source**

```bash
grep -r "AxonFlowEngine\|AxonFlowConfig" src/axonflow --include="*.py" | grep -v "__pycache__"
```

Expected: no output

- [ ] **Step 6: Quick smoke test — imports resolve**

```bash
cd /Users/limingyang3/Documents/AxonFlow && python -c "from axonflow.engine import AxonFlowEngine; from axonflow.config.models import AxonFlowConfig; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Run the test suite**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: `114 passed`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: rename Python package axonflow → axonflow, AxonFlowEngine → AxonFlowEngine"
```

---

## Task 4: Update display strings, CLI name, Redis prefix, config default path

**Files:**
- Modify: `src/axonflow/__init__.py` — module docstring
- Modify: `src/axonflow/__main__.py` — docstring
- Modify: `src/axonflow/cli/app.py` — display strings (`"AxonFlow"` → `"AxonFlow"`, typer name `"axonflow"` → `"axonflow"`)
- Modify: `src/axonflow/config/defaults.py` — `REDIS_KEY_PREFIX = "axonflow"` → `"axonflow"`
- Modify: `src/axonflow/config/loader.py` — default path `"config/axonflow.yaml"` → `"config/axonflow.yaml"`
- Modify: `src/axonflow/engine.py` — docstring display string

- [ ] **Step 1: Update `src/axonflow/__init__.py`**

Replace the entire file content:

```python
"""AxonFlow — 基于多智能体的自治工作流引擎"""

__version__ = "0.1.0"
```

- [ ] **Step 2: Update `src/axonflow/__main__.py`**

Replace the entire file content:

```python
"""Allow running AxonFlow as: python -m axonflow"""

from axonflow.cli.app import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update display strings in `src/axonflow/cli/app.py`**

Run:

```bash
sed -i '' 's/AxonFlow/AxonFlow/g' src/axonflow/cli/app.py
sed -i '' "s/name=\"axonflow\"/name=\"axonflow\"/g" src/axonflow/cli/app.py
```

- [ ] **Step 4: Update Redis prefix in `src/axonflow/config/defaults.py`**

```bash
sed -i '' 's/REDIS_KEY_PREFIX = "axonflow"/REDIS_KEY_PREFIX = "axonflow"/g' src/axonflow/config/defaults.py
```

- [ ] **Step 5: Update default config path in `src/axonflow/config/loader.py`**

```bash
sed -i '' 's|"config/axonflow.yaml"|"config/axonflow.yaml"|g' src/axonflow/config/loader.py
```

- [ ] **Step 6: Update docstring in engine.py**

```bash
sed -i '' 's/AxonFlow 引擎/AxonFlow 引擎/g' src/axonflow/engine.py
sed -i '' 's/AxonFlow/AxonFlow/g' src/axonflow/engine.py
```

- [ ] **Step 7: Verify no remaining `axonflow` (lowercase) or `AxonFlow` references in Python source (except intentional)**

```bash
grep -rn "axonflow\|AxonFlow" src/axonflow --include="*.py" | grep -v "__pycache__"
```

Expected: empty (all renamed)

- [ ] **Step 8: Run the test suite**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: `114 passed`

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: update display strings, CLI name, Redis prefix, config default path to AxonFlow"
```

---

## Task 5: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current pyproject.toml to confirm exact lines**

Current content (confirmed):
```toml
name = "axonflow"
authors = [{ name = "AxonFlow Contributors" }]
axonflow = "axonflow.cli.app:main"
packages = ["src/axonflow"]
```

- [ ] **Step 2: Update pyproject.toml**

```bash
sed -i '' 's/^name = "axonflow"/name = "axonflow"/' pyproject.toml
sed -i '' 's/AxonFlow Contributors/AxonFlow Contributors/' pyproject.toml
sed -i '' 's|axonflow = "axonflow.cli.app:main"|axonflow = "axonflow.cli.app:main"|' pyproject.toml
sed -i '' 's|packages = \["src/axonflow"\]|packages = ["src/axonflow"]|' pyproject.toml
```

- [ ] **Step 3: Verify the changes**

```bash
grep -n "axonflow\|AxonFlow" pyproject.toml
```

Expected: no output (all references updated)

- [ ] **Step 4: Verify package is importable after pyproject change (reinstall editable)**

```bash
pip install -e . -q && python -c "import axonflow; print(axonflow.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 5: Run the test suite**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: `114 passed`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml
git commit -m "refactor: rename package entry in pyproject.toml — axonflow → axonflow"
```

---

## Task 6: Rename config/axonflow.yaml → config/axonflow.yaml

**Files:**
- Rename: `config/axonflow.yaml` → `config/axonflow.yaml`

Note: `config/axonflow.yaml` has local modifications (API key, model name) that are NOT committed. The file itself is tracked by git (its committed version has no keys). We rename the tracked file; the local modifications travel with it.

- [ ] **Step 1: Rename with git mv**

```bash
git mv config/axonflow.yaml config/axonflow.yaml
```

- [ ] **Step 2: Verify**

```bash
ls config/axonflow.yaml && git status --short config/
```

Expected: file exists, git shows rename

- [ ] **Step 3: Verify loader now picks up the correct file**

The loader's default path was already updated to `"config/axonflow.yaml"` in Task 4 Step 5.

```bash
python -c "
from axonflow.config.loader import load_global_config
cfg = load_global_config('config/axonflow.yaml')
print('workspace_dir:', cfg.workspace_dir)
"
```

Expected: prints workspace_dir without error

- [ ] **Step 4: Run the test suite**

```bash
python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: `114 passed`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename config/axonflow.yaml → config/axonflow.yaml"
```

---

## Task 7: Update docker-compose.yml

**Files:**
- Modify: `docker/docker-compose.yml`

- [ ] **Step 1: Update service name and any references**

```bash
sed -i '' 's/axonflow:/axonflow:/g' docker/docker-compose.yml
sed -i '' 's/AxonFlow/AxonFlow/g' docker/docker-compose.yml
```

- [ ] **Step 2: Verify**

```bash
grep -n "axonflow\|AxonFlow" docker/docker-compose.yml
```

Expected: no output

- [ ] **Step 3: Commit**

```bash
git add docker/docker-compose.yml
git commit -m "refactor: rename docker-compose service axonflow → axonflow"
```

---

## Task 8: Update documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/PRD.md`
- Modify: `docs/TECHNICAL_DESIGN.md`
- Modify: `docs/PROJECT_STRUCTURE.md`
- Modify: `docs/specs/2026-04-02-tool-calling-and-skill-system-design.md`
- Modify: `docs/superpowers/plans/2026-04-02-phase1-tool-calling-skill-system.md`

- [ ] **Step 1: Replace AxonFlow with AxonFlow in all doc files**

```bash
sed -i '' 's/AxonFlow/AxonFlow/g' README.md
sed -i '' 's/axonflow/axonflow/g' README.md
sed -i '' 's/AxonFlow/AxonFlow/g' docs/PRD.md
sed -i '' 's/axonflow/axonflow/g' docs/PRD.md
sed -i '' 's/AxonFlow/AxonFlow/g' docs/TECHNICAL_DESIGN.md
sed -i '' 's/axonflow/axonflow/g' docs/TECHNICAL_DESIGN.md
sed -i '' 's/AxonFlow/AxonFlow/g' docs/PROJECT_STRUCTURE.md
sed -i '' 's/axonflow/axonflow/g' docs/PROJECT_STRUCTURE.md
sed -i '' 's/AxonFlow/AxonFlow/g' docs/specs/2026-04-02-tool-calling-and-skill-system-design.md
sed -i '' 's/axonflow/axonflow/g' docs/specs/2026-04-02-tool-calling-and-skill-system-design.md
sed -i '' 's/AxonFlow/AxonFlow/g' docs/superpowers/plans/2026-04-02-phase1-tool-calling-skill-system.md
sed -i '' 's/axonflow/axonflow/g' docs/superpowers/plans/2026-04-02-phase1-tool-calling-skill-system.md
```

- [ ] **Step 2: Verify no remaining axonflow/AxonFlow references in docs**

```bash
grep -rn "axonflow\|AxonFlow" README.md docs/ 2>/dev/null | grep -v "__pycache__"
```

Expected: no output

- [ ] **Step 3: Final full test suite run**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -15
```

Expected: `114 passed`

- [ ] **Step 4: Final check — no remaining axonflow references anywhere (excluding git history and .git dir)**

```bash
grep -rn "axonflow\|AxonFlow" . \
  --include="*.py" --include="*.yaml" --include="*.yml" \
  --include="*.toml" --include="*.md" --include="*.sh" \
  --exclude-dir=".git" --exclude-dir="__pycache__" \
  | grep -v "config/axonflow.yaml"
```

Expected: no output (or only intentional occurrences like git log messages)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: update all documentation references AxonFlow → AxonFlow"
```

---

## Summary

| Task | What | Commit |
|------|------|--------|
| 1 | `git mv src/axonflow → src/axonflow` | (staged, committed with Task 2-3) |
| 2 | All import statements updated | (staged, committed with Task 3) |
| 3 | Class names renamed + tests pass | `refactor: rename Python package axonflow → axonflow` |
| 4 | Display strings, CLI, Redis, config path | `refactor: update display strings, CLI name, Redis prefix, config default path` |
| 5 | pyproject.toml | `refactor: rename package entry in pyproject.toml` |
| 6 | config/axonflow.yaml → config/axonflow.yaml | `refactor: rename config/axonflow.yaml → config/axonflow.yaml` |
| 7 | docker-compose.yml | `refactor: rename docker-compose service axonflow → axonflow` |
| 8 | All docs | `docs: update all documentation references AxonFlow → AxonFlow` |

**Total: 6 commits, 114 tests must pass throughout**
