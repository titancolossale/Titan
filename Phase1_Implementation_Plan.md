# Phase 1 — Architecture Cleanup: Implementation Plan

**Document type:** Executable engineering task breakdown  
**Phase:** Titan V2 — Phase 1 (Architecture Cleanup)  
**Target version:** v0.1.0 (foundation release)  
**Date:** 2026-06-23  
**Status:** Ready for execution — one task per chat session recommended  

**Source authority (read before starting any task):**

| Document | Use when |
|----------|----------|
| `Titan_V2_Roadmap.md` | Phase scope, definition of done, invariants |
| `Brain_Audit.md` | P0 bugs, duplicate instances, file inventory |
| `Titan_Context.md` | Current runtime truth, v0.1 consolidation goals |
| `Titan_Blueprint.md` | Product constraints, target directories |
| `.cursor/rules/titan.mdc` | Dependency direction, testing policy, coding standards |

**Phase 1 scope boundary (do NOT do in Phase 1):**

- Prompt builder / Brain pipeline redesign → Phase 2
- Retrieved memory in prompt (vs full dump) → Phase 2
- Identity/constitution in LLM instructions → Phase 2
- User-aware memory writes (Nolan/Ibrahim) → Phase 3
- Dynamic context sync with state/mission → Phase 4
- Unified agent routing registry → Phase 5
- LLM-backed agents → Phase 5

**Phase 1 invariants (must hold after sign-off):**

1. Exactly **one** `AgentManager` instance per process  
2. Exactly **one** agent orchestration path per user turn (`TaskOrchestrator` inside Brain only)  
3. `Brain.__init__` receives shared dependencies from `Titan` — no `AgentManager()` or `ContextManager()` inside Brain  
4. REPL survives LLM and Brain exceptions  
5. `TaskEvaluator` does not advance mission on `"continue"` alone  
6. Casual messages do not auto-create missions when none is active  
7. Dead modules `core/action_manager.py` and `core/context.py` removed with zero orphan imports  
8. `tests/` exists with ≥15 tests; `pytest tests/ -v` passes  
9. Structured logging infrastructure exists; modified hot-path files use `logging` not new permanent `print()`  

---

## How to Use This Plan

1. Execute tasks **in numeric ID order** unless a task explicitly allows parallel work.  
2. Complete **verification checklist** before marking a task done.  
3. If verification fails, use **rollback strategy**, fix, re-run — do not skip to next task.  
4. At the start of each chat session, state: `Executing task P1-XXX` and paste that task block.  
5. After each task, update `CHANGELOG.md` if the task produces user-visible or architectural change.  
6. **Back up `data/*.json`** before tasks P1-080+ (TaskEvaluator and mission gating touch live mission state).

**Difficulty scale:** Easy · Medium · Hard  
**Risk scale:** Low · Medium · High  

---

## Task Dependency Overview

```
Track A: Foundation (P1-001 → P1-019)
    │
    ├── Track B: Logging (P1-020 → P1-029) ──┐
    │                                        │
    ├── Track C: Package hygiene (P1-030 → P1-039) ──┤
    │                                                │
    └── Track D: Dead code removal (P1-040 → P1-049) ┘
                              │
                              ▼
              Track E: Dependency injection (P1-050 → P1-069)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    Track F: Remove      Track G: P0 bugs   Track H: MemoryFacade
    double agents        (P1-080 → P1-119)  stub (P1-120 → P1-124)
    (P1-070 → P1-079)            │
              │                  │
              └────────┬─────────┘
                       ▼
         Track I: Logging migration (P1-130 → P1-139)
                       │
                       ▼
         Track J: Release hygiene (P1-140 → P1-149)
                       │
                       ▼
         Track K: Phase sign-off (P1-150 → P1-155)
```

---

## Track A — Foundation & Test Scaffold

### P1-001 — Create CHANGELOG.md scaffold

| Field | Value |
|-------|-------|
| **Purpose** | Establish change documentation before any code edits; Phase 1 sign-off requires changelog note. |
| **Files involved** | `CHANGELOG.md` (new) |
| **Dependencies** | None |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `CHANGELOG.md` exists with header, `[Unreleased]` section, and placeholder for v0.1.0 Phase 1 entry.

**Verification checklist:**
- [ ] File exists at repo root
- [ ] Contains version policy note (semver, Phase 1 = v0.1.0)
- [ ] No secrets or `data/` contents in file

**Rollback strategy:** Delete `CHANGELOG.md`.

---

### P1-002 — Document data backup procedure for Phase 1 testing

| Field | Value |
|-------|-------|
| **Purpose** | Prevent corruption of live mission/memory JSON during TaskEvaluator and mission-gating tests. |
| **Files involved** | `CHANGELOG.md` or inline note in this plan (no code) |
| **Dependencies** | P1-001 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Written procedure: copy `data/titan_mission.json`, `data/titan_state.json`, `data/long_term_memory.json` to `data/backups/YYYYMMDD/` before manual testing of P1-080+.

**Verification checklist:**
- [ ] Backup directory convention documented
- [ ] Restore steps documented (`copy backups back to data/`)

**Rollback strategy:** N/A (documentation only).

---

### P1-003 — Baseline instantiation audit (grep inventory)

| Field | Value |
|-------|-------|
| **Purpose** | Capture pre-Phase-1 duplicate instantiation locations; used to verify P1-150 grep sign-off. |
| **Files involved** | None (read-only grep); record results in `CHANGELOG.md` `[Unreleased]` notes or task comment |
| **Dependencies** | None |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Documented list of every `AgentManager()`, `ContextManager()`, `StateManager()`, `MissionManager()`, `LongTermMemory()` instantiation in repo.

**Known baseline (2026-06-23):**
- `core/titan.py`: `ContextManager()`, `AgentManager()`
- `brain/brain.py`: `ContextManager()`, `AgentManager()`, `StateManager()`, `MissionManager()`, `LongTermMemory()`

**Verification checklist:**
- [ ] Grep run: `AgentManager\(`, `ContextManager\(`, `StateManager\(`, `MissionManager\(`, `LongTermMemory\(`
- [ ] Results recorded for comparison at P1-152

**Rollback strategy:** N/A.

---

### P1-010 — Create `tests/` directory structure

| Field | Value |
|-------|-------|
| **Purpose** | Satisfy rulebook Section 11; enable regression tests for P0 fixes. |
| **Files involved** | `tests/__init__.py` (new, may be empty) |
| **Dependencies** | None |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `tests/` directory exists at repo root.

**Verification checklist:**
- [ ] Directory present
- [ ] Does not modify production import paths yet

**Rollback strategy:** Delete `tests/` directory.

---

### P1-011 — Add pytest to requirements.txt

| Field | Value |
|-------|-------|
| **Purpose** | Pin test runner dependency for CI and local dev. |
| **Files involved** | `requirements.txt` |
| **Dependencies** | P1-010 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `requirements.txt` includes `pytest` with minimum version comment (e.g. `pytest>=8.0`).

**Verification checklist:**
- [ ] `pip install -r requirements.txt` succeeds in venv
- [ ] `pytest --version` runs

**Rollback strategy:** Revert `requirements.txt` line.

---

### P1-012 — Create `tests/conftest.py` with JSON manager fixtures

| Field | Value |
|-------|-------|
| **Purpose** | Provide `tmp_path`-isolated JSON paths for manager tests; never write to real `data/`. |
| **Files involved** | `tests/conftest.py` (new) |
| **Dependencies** | P1-010, P1-011 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Pytest fixtures e.g. `state_manager(tmp_path)`, `mission_manager(tmp_path)` returning managers pointed at temp files.

**Verification checklist:**
- [ ] Fixtures use `tmp_path` only
- [ ] No reads/writes to `data/` during fixture setup
- [ ] `pytest tests/ --collect-only` succeeds

**Rollback strategy:** Delete `tests/conftest.py`.

---

### P1-013 — Smoke test: import all production modules

| Field | Value |
|-------|-------|
| **Purpose** | Catch import/circular dependency regressions early on every change. |
| **Files involved** | `tests/test_imports.py` (new) |
| **Dependencies** | P1-010, P1-011 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Test imports `core.titan`, `brain.brain`, all managers, all agents without error.

**Verification checklist:**
- [ ] `pytest tests/test_imports.py -v` passes
- [ ] Test count ≥ 1

**Rollback strategy:** Delete test file.

---

### P1-014 — Baseline tests: StateManager load/save round-trip

| Field | Value |
|-------|-------|
| **Purpose** | Regression safety before DI moves StateManager ownership. |
| **Files involved** | `tests/test_state_manager.py` (new), `core/state_manager.py` (read) |
| **Dependencies** | P1-012 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Tests cover: default schema on missing file, save/load round-trip, `update_after_response` updates last messages.

**Verification checklist:**
- [ ] ≥ 3 test cases
- [ ] All use `tmp_path`
- [ ] `pytest tests/test_state_manager.py -v` passes

**Rollback strategy:** Delete test file.

---

### P1-015 — Baseline tests: MissionManager load/save and step completion

| Field | Value |
|-------|-------|
| **Purpose** | Regression safety before mission gating and TaskEvaluator changes. |
| **Files involved** | `tests/test_mission_manager.py` (new), `core/mission_manager.py` (read) |
| **Dependencies** | P1-012 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Tests cover: inactive default, `create_mission`, `complete_current_step`, `create_mission_from_message` keyword paths (record current behavior).

**Verification checklist:**
- [ ] ≥ 4 test cases
- [ ] All use `tmp_path`
- [ ] `pytest tests/test_mission_manager.py -v` passes

**Rollback strategy:** Delete test file.

---

### P1-016 — Baseline tests: TaskEvaluator current behavior snapshot

| Field | Value |
|-------|-------|
| **Purpose** | Capture failing cases BEFORE fix (TDD); `"continue"` should fail after P1-080. |
| **Files involved** | `tests/test_task_evaluator.py` (new), `brain/task_evaluator.py` (read) |
| **Dependencies** | P1-012 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Parametrized tests documenting current behavior including known bugs (`continue` → True today). Mark bug cases with comment `# P0: must become False in P1-080`.

**Verification checklist:**
- [ ] Tests pass against current code OR expected failures documented with `pytest.mark.xfail` for post-fix flip
- [ ] ≥ 5 parametrized cases

**Rollback strategy:** Delete test file.

---

### P1-017 — Baseline tests: MemoryRetriever keyword relevance

| Field | Value |
|-------|-------|
| **Purpose** | Rulebook Section 11.3 minimum coverage; safe before any memory changes in later phases. |
| **Files involved** | `tests/test_memory_retriever.py` (new), `memory/memory_retriever.py` (read) |
| **Dependencies** | P1-012 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Tests for empty memory, matching note, no match, titan block match.

**Verification checklist:**
- [ ] ≥ 3 test cases
- [ ] `pytest tests/test_memory_retriever.py -v` passes

**Rollback strategy:** Delete test file.

---

### P1-018 — Baseline tests: AgentSelector routing smoke

| Field | Value |
|-------|-------|
| **Purpose** | Document routing behavior before Phase 5 unification; supports orchestrator tests. |
| **Files involved** | `tests/test_agent_selector.py` (new), `agents/agent_selector.py` (read) |
| **Dependencies** | P1-012 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Keyword → agent name tests for coding, research, planning, reasoning, default.

**Verification checklist:**
- [ ] ≥ 5 routing cases
- [ ] `pytest tests/test_agent_selector.py -v` passes

**Rollback strategy:** Delete test file.

---

### P1-019 — Confirm baseline test count ≥ 10 before DI work

| Field | Value |
|-------|-------|
| **Purpose** | Gate: do not refactor wiring without test safety net. |
| **Files involved** | All `tests/test_*.py` |
| **Dependencies** | P1-013 through P1-018 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `pytest tests/ -v` reports ≥ 10 passing tests (xfail allowed for P0 cases).

**Verification checklist:**
- [ ] Full suite green (or xfail documented)
- [ ] Test count recorded in CHANGELOG

**Rollback strategy:** N/A.

---

## Track B — Logging Infrastructure

### P1-020 — Create `logs/` directory

| Field | Value |
|-------|-------|
| **Purpose** | Target location for structured log files per rulebook Section 18. |
| **Files involved** | `logs/.gitkeep` (new) |
| **Dependencies** | None |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `logs/` exists; `.gitignore` updated to ignore `logs/*.log` but keep directory (add if missing).

**Verification checklist:**
- [ ] Directory exists
- [ ] `.gitignore` excludes `logs/*.log` (not entire `logs/` if `.gitkeep needed`)

**Rollback strategy:** Remove directory and `.gitignore` entry.

---

### P1-021 — Implement `core/logging_config.py`

| Field | Value |
|-------|-------|
| **Purpose** | Central logging setup: rotating file handler + console handler. |
| **Files involved** | `core/logging_config.py` (new) |
| **Dependencies** | P1-020 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Function `setup_logging(log_level: str, log_dir: Path) -> None` configures root logger with:
- File: `logs/titan.log` (RotatingFileHandler, e.g. 5MB × 3)
- Console handler for development
- Format: timestamp, module, level, message

**Verification checklist:**
- [ ] Import and call from REPL/test produces log line in file and console
- [ ] No secrets logged in setup
- [ ] Uses stdlib `logging` only

**Rollback strategy:** Delete module; remove callers.

---

### P1-022 — Add feature flags to `config/settings.py`

| Field | Value |
|-------|-------|
| **Purpose** | Support `DEBUG_BRAIN` and `LOG_LEVEL` per roadmap and rulebook Section 19.4. |
| **Files involved** | `config/settings.py` |
| **Dependencies** | None |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:**
```python
import os
LOG_LEVEL = os.getenv("TITAN_LOG_LEVEL", "INFO")
DEBUG_BRAIN = os.getenv("TITAN_DEBUG_BRAIN", "false").lower() == "true"
```

**Verification checklist:**
- [ ] Defaults preserve current behavior (INFO, DEBUG_BRAIN false)
- [ ] No secrets in settings.py
- [ ] Existing imports (`TITAN_NAME`, `VERSION`, `CREATOR`) unchanged

**Rollback strategy:** Revert settings.py additions.

---

### P1-023 — Wire logging at application entry

| Field | Value |
|-------|-------|
| **Purpose** | Ensure logging active before Titan REPL loop. |
| **Files involved** | `main.py`, `core/logging_config.py`, `config/settings.py` |
| **Dependencies** | P1-021, P1-022 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `main.py` calls `setup_logging(LOG_LEVEL, ...)` before `Titan()` instantiation.

**Verification checklist:**
- [ ] `python main.py` creates/append `logs/titan.log`
- [ ] Startup message logged at INFO
- [ ] REPL still works

**Rollback strategy:** Remove setup call from `main.py`.

---

### P1-024 — Add test for logging configuration smoke

| Field | Value |
|-------|-------|
| **Purpose** | Prevent logging regressions. |
| **Files involved** | `tests/test_logging_config.py` (new) |
| **Dependencies** | P1-021, P1-023 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Test calls `setup_logging` with temp log dir; asserts log file created after logger.info.

**Verification checklist:**
- [ ] Uses tmp_path for log directory
- [ ] Test passes in isolation

**Rollback strategy:** Delete test file.

---

## Track C — Package & Developer Hygiene

### P1-030 — Add `__init__.py` to all packages

| Field | Value |
|-------|-------|
| **Purpose** | Enable reliable test imports and future packaging (roadmap Phase 1 objective 6). |
| **Files involved** | `config/__init__.py`, `core/__init__.py`, `brain/__init__.py`, `agents/__init__.py`, `memory/__init__.py`, `context/__init__.py`, `tools/__init__.py` (all new, empty or minimal) |
| **Dependencies** | P1-019 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** All seven package directories are importable as packages.

**Verification checklist:**
- [ ] `python -c "from brain.brain import Brain"` works from project root
- [ ] `pytest tests/ -v` still passes
- [ ] No business logic inside `__init__.py` files

**Rollback strategy:** Delete new `__init__.py` files.

---

### P1-031 — Create `.env.example`

| Field | Value |
|-------|-------|
| **Purpose** | Document required secrets without committing `.env`. |
| **Files involved** | `.env.example` (new) |
| **Dependencies** | None |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Template with:
```
OPENAI_API_KEY=your_key_here
TITAN_LOG_LEVEL=INFO
TITAN_DEBUG_BRAIN=false
```

**Verification checklist:**
- [ ] No real API keys
- [ ] `.env` remains gitignored
- [ ] Variables match `brain/llm.py` and `config/settings.py`

**Rollback strategy:** Delete file.

---

### P1-032 — Add minimal README setup section

| Field | Value |
|-------|-------|
| **Purpose** | Document venv, install, env setup, run, test for Nolan's Windows environment. |
| **Files involved** | `README.md` (new or update if exists) |
| **Dependencies** | P1-031 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** README sections: Prerequisites (Python 3.10+), Setup, Configure `.env`, Run `python main.py`, Run tests `pytest tests/ -v`, PYTHONPATH note (project root).

**Verification checklist:**
- [ ] Commands are copy-pasteable on Windows PowerShell
- [ ] No secrets in README

**Rollback strategy:** Revert README changes.

---

### P1-033 — Add `pyproject.toml` minimal pytest configuration

| Field | Value |
|-------|-------|
| **Purpose** | Document PYTHONPATH strategy; configure pytest test paths. |
| **Files involved** | `pyproject.toml` (new) |
| **Dependencies** | P1-030 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, `pythonpath = ["."]`.

**Verification checklist:**
- [ ] `pytest` discovers tests from repo root without manual PYTHONPATH
- [ ] Does not break `python main.py`

**Rollback strategy:** Delete `pyproject.toml`; rely on README PYTHONPATH note.

---

## Track D — Dead Code Removal

### P1-040 — Verify zero imports of `core/action_manager.py`

| Field | Value |
|-------|-------|
| **Purpose** | Safe deletion gate per rulebook Section 10.4. |
| **Files involved** | `core/action_manager.py` (read), entire repo (grep) |
| **Dependencies** | P1-019 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Grep confirms no `from core.action_manager` or `import action_manager` in `.py` files.

**Verification checklist:**
- [ ] Grep result empty for production imports
- [ ] Documented in task notes

**Rollback strategy:** N/A.

---

### P1-041 — Verify zero imports of `core/context.py`

| Field | Value |
|-------|-------|
| **Purpose** | Safe deletion gate; avoid confusion with `context/context_manager.py`. |
| **Files involved** | `core/context.py` (read), entire repo (grep) |
| **Dependencies** | P1-019 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Grep confirms no imports of `core.context` or `from core.context import Context`.

**Verification checklist:**
- [ ] Grep result empty for production imports

**Rollback strategy:** N/A.

---

### P1-042 — Delete `core/action_manager.py`

| Field | Value |
|-------|-------|
| **Purpose** | Retire dead module per Phase 1 objective 3. |
| **Files involved** | `core/action_manager.py` (delete) |
| **Dependencies** | P1-040 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** File removed; no import errors.

**Verification checklist:**
- [ ] File deleted
- [ ] `pytest tests/ -v` passes
- [ ] `python main.py` starts (manual smoke)
- [ ] CHANGELOG notes deletion

**Rollback strategy:** `git checkout -- core/action_manager.py` or restore from git history.

---

### P1-043 — Delete `core/context.py`

| Field | Value |
|-------|-------|
| **Purpose** | Retire duplicate legacy context; active context remains `context/context_manager.py`. |
| **Files involved** | `core/context.py` (delete) |
| **Dependencies** | P1-041 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** File removed; no import errors.

**Verification checklist:**
- [ ] File deleted
- [ ] `pytest tests/ -v` passes
- [ ] `python main.py` starts
- [ ] CHANGELOG notes deletion

**Rollback strategy:** Restore file from git.

---

### P1-044 — Add test guarding against dead module resurrection

| Field | Value |
|-------|-------|
| **Purpose** | CI guard: ensure deleted modules stay deleted. |
| **Files involved** | `tests/test_no_dead_modules.py` (new) |
| **Dependencies** | P1-042, P1-043 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Test asserts `core/action_manager.py` and `core/context.py` do not exist.

**Verification checklist:**
- [ ] Test passes
- [ ] Added to full suite

**Rollback strategy:** Delete test if modules restored intentionally.

---

## Track E — Dependency Injection (Composition Root)

**Design target for `Brain.__init__` (final state after P1-069):**

```python
def __init__(
    self,
    *,
    agent_manager: AgentManager,
    context_manager: ContextManager,
    state_manager: StateManager,
    mission_manager: MissionManager,
    long_term_memory: LongTermMemory,
    llm: LLM | None = None,  # optional: Brain may construct LLM if not injected
) -> None:
```

Brain-internal modules (`Decision`, `Reasoning`, `Planning`, etc.) may remain Brain-owned unless they need shared state — Phase 1 scope is **shared managers only**.

**Design target for `Titan.__init__` (final state):**

```python
self.agents = AgentManager()
self.context = ContextManager()
self.state = StateManager()
self.mission = MissionManager()
self.long_memory = LongTermMemory()
self.brain = Brain(
    agent_manager=self.agents,
    context_manager=self.context,
    state_manager=self.state,
    mission_manager=self.mission,
    long_term_memory=self.long_memory,
)
```

---

### P1-050 — Design review: document Brain constructor contract

| Field | Value |
|-------|-------|
| **Purpose** | Lock API before incremental injection; prevent partial inconsistent states across chats. |
| **Files involved** | This plan (reference only); optional comment block in `brain/brain.py` docstring |
| **Dependencies** | P1-042, P1-043 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Agreed list of injected deps vs Brain-owned subs; recorded in Brain class docstring.

**Verification checklist:**
- [ ] Docstring lists required injected managers
- [ ] Matches design target above

**Rollback strategy:** Remove docstring addition.

---

### P1-051 — Inject `AgentManager`: add optional parameter to Brain

| Field | Value |
|-------|-------|
| **Purpose** | First DI step with backward compatibility. |
| **Files involved** | `brain/brain.py` |
| **Dependencies** | P1-050 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** `Brain.__init__(self, agent_manager=None)` — if None, instantiate (temporary); wire `task_manager` and `task_orchestrator` from injected instance.

**Verification checklist:**
- [ ] Existing `Brain()` without args still works
- [ ] `pytest tests/ -v` passes

**Rollback strategy:** Revert Brain `__init__` signature.

---

### P1-052 — Titan passes shared `AgentManager` to Brain

| Field | Value |
|-------|-------|
| **Purpose** | First shared instance wiring. |
| **Files involved** | `core/titan.py`, `brain/brain.py` |
| **Dependencies** | P1-051 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** `Titan.__init__` creates `self.agents` before Brain; `self.brain = Brain(agent_manager=self.agents)`.

**Verification checklist:**
- [ ] `id(titan.agents) == id(titan.brain.agent_manager)`
- [ ] `python main.py` works
- [ ] Tests pass

**Rollback strategy:** Revert Titan Brain construction line.

---

### P1-053 — Test: AgentManager identity equality

| Field | Value |
|-------|-------|
| **Purpose** | Automated guard for duplicate AgentManager (P0). |
| **Files involved** | `tests/test_composition.py` (new) |
| **Dependencies** | P1-052 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Test instantiates `Titan()` (or factory without REPL) and asserts same `AgentManager` instance.

**Verification checklist:**
- [ ] Test passes
- [ ] Uses mock or skips LLM if needed (no API call in test)

**Rollback strategy:** Delete test.

---

### P1-054 — Inject `ContextManager` into Brain from Titan

| Field | Value |
|-------|-------|
| **Purpose** | Eliminate duplicate ContextManager instance. |
| **Files involved** | `brain/brain.py`, `core/titan.py` |
| **Dependencies** | P1-052 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** `Brain(context_manager=...)` required or optional-then-required; Titan passes `self.context`.

**Verification checklist:**
- [ ] `id(titan.context) == id(titan.brain.context_manager)`
- [ ] Startup banner context unchanged
- [ ] Tests pass

**Rollback strategy:** Revert both files.

---

### P1-055 — Test: ContextManager identity equality

| Field | Value |
|-------|-------|
| **Purpose** | Automated guard for duplicate ContextManager. |
| **Files involved** | `tests/test_composition.py` |
| **Dependencies** | P1-054 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Composition test extended for context manager.

**Verification checklist:**
- [ ] Assertion passes

**Rollback strategy:** Revert test addition.

---

### P1-056 — Inject `StateManager` into Brain from Titan

| Field | Value |
|-------|-------|
| **Purpose** | Single state JSON owner; prepares Phase 4 context sync. |
| **Files involved** | `brain/brain.py`, `core/titan.py` |
| **Dependencies** | P1-054 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** Titan constructs `self.state = StateManager()`; Brain receives it.

**Verification checklist:**
- [ ] State updates in Brain persist to same file as before
- [ ] `pytest tests/test_state_manager.py` passes
- [ ] Identity test optional but recommended

**Rollback strategy:** Revert injection; Brain re-instantiates StateManager.

---

### P1-057 — Inject `MissionManager` into Brain from Titan

| Field | Value |
|-------|-------|
| **Purpose** | Single mission JSON owner; mission gating tests use same instance. |
| **Files involved** | `brain/brain.py`, `core/titan.py` |
| **Dependencies** | P1-056 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** Titan constructs `self.mission = MissionManager()`; Brain receives it.

**Verification checklist:**
- [ ] Mission auto-create still works (until P1-090 changes behavior)
- [ ] `pytest tests/test_mission_manager.py` passes

**Rollback strategy:** Revert injection.

---

### P1-058 — Inject `LongTermMemory` into Brain from Titan

| Field | Value |
|-------|-------|
| **Purpose** | Single long-term memory JSON owner; prepares Phase 3 facade. |
| **Files involved** | `brain/brain.py`, `core/titan.py` |
| **Dependencies** | P1-057 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** Titan constructs `self.long_memory = LongTermMemory()`; Brain receives it.

**Verification checklist:**
- [ ] Memory writes in Brain hit same JSON file
- [ ] No duplicate `LongTermMemory()` in Brain after this task

**Rollback strategy:** Revert injection.

---

### P1-059 — Remove fallback instantiation from Brain for injected managers

| Field | Value |
|-------|-------|
| **Purpose** | Enforce composition root pattern; fail fast if deps missing. |
| **Files involved** | `brain/brain.py` |
| **Dependencies** | P1-051 through P1-058 |
| **Difficulty** | Medium |
| **Risk** | High |

**Expected result:** Brain `__init__` requires keyword-only injected managers; no `AgentManager()` etc. inside Brain.

**Verification checklist:**
- [ ] Grep `brain/brain.py`: zero `AgentManager()`, `ContextManager()`, `StateManager()`, `MissionManager()`, `LongTermMemory()`
- [ ] `Brain()` without args raises `TypeError`
- [ ] Titan still starts
- [ ] All tests pass

**Rollback strategy:** Restore optional defaults temporarily.

---

### P1-060 — Add factory helper for tests (optional Brain construction)

| Field | Value |
|-------|-------|
| **Purpose** | Tests need Brain without full Titan REPL; avoid duplicating wiring logic. |
| **Files involved** | `tests/conftest.py` or `tests/brain_factory.py` (new) |
| **Dependencies** | P1-059 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Fixture `brain(tmp_path)` builds all managers with temp JSON paths + mocked `LLM`.

**Verification checklist:**
- [ ] Fixture used in at least one test
- [ ] No live OpenAI calls

**Rollback strategy:** Remove fixture; tests construct manually.

---

### P1-061 — Composition test: grep zero duplicate manager constructors

| Field | Value |
|-------|-------|
| **Purpose** | Automated documentation of DI completion. |
| **Files involved** | `tests/test_composition.py` |
| **Dependencies** | P1-059 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Test reads `brain/brain.py` source (or imports inspect) and asserts no forbidden constructor calls.

**Verification checklist:**
- [ ] Test passes after P1-059

**Rollback strategy:** Remove test.

---

### P1-062 — Reorder Titan.__init__ for readability

| Field | Value |
|-------|-------|
| **Purpose** | Composition root clarity: managers first, then Brain, then auxiliary. |
| **Files involved** | `core/titan.py` |
| **Dependencies** | P1-058 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Init order: config attrs → managers → brain → tools → conversation → memory (short-term).

**Verification checklist:**
- [ ] No behavior change
- [ ] `python main.py` works

**Rollback strategy:** Revert formatting only.

---

## Track F — Remove Double Agent Execution

### P1-070 — Remove `auto_execute` from REPL loop

| Field | Value |
|-------|-------|
| **Purpose** | Fix P0 double agent execution (Brain_Audit §9.2, §13.1). |
| **Files involved** | `core/titan.py` |
| **Dependencies** | P1-052 (shared AgentManager must already be wired) |
| **Difficulty** | Easy |
| **Risk** | Medium |

**Expected result:** Delete lines calling `self.agents.auto_execute(question)` and associated prints.

**Verification checklist:**
- [ ] REPL loop calls only `self.brain.think(question)` for agent work
- [ ] No second agent output block after response
- [ ] `python main.py` manual smoke: one orchestrator block in console per turn

**Rollback strategy:** Restore `auto_execute` call (temporary only).

---

### P1-071 — Evaluate whether Titan needs `self.agents` attribute

| Field | Value |
|-------|-------|
| **Purpose** | Avoid orphan attribute; Titan may only hold agents for injection reference. |
| **Files involved** | `core/titan.py` |
| **Dependencies** | P1-070 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Decision documented: keep `self.agents` as composition root reference (recommended) OR access only via `self.brain.agent_manager`. If removed, ensure Brain injection still works.

**Verification checklist:**
- [ ] No dead code referencing removed attribute
- [ ] CHANGELOG notes orchestration policy: **Brain TaskOrchestrator only**

**Rollback strategy:** N/A.

---

### P1-072 — Test: single agent execution per turn

| Field | Value |
|-------|-------|
| **Purpose** | Regression test for P0 invariant. |
| **Files involved** | `tests/test_single_agent_path.py` (new), `brain/brain.py`, `core/task_orchestrator.py` |
| **Dependencies** | P1-070, P1-060 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Mock `AgentManager.execute`; call `brain.think("test code python")`; assert `execute` call count equals number of tasks from TaskManager (not doubled); assert Titan REPL path does not call `auto_execute` (source inspection test acceptable).

**Verification checklist:**
- [ ] Mock LLM returns fixed string
- [ ] Execute call count matches orchestrator task list length exactly once per think
- [ ] Test passes

**Rollback strategy:** Delete test.

---

### P1-073 — Test: Titan REPL does not call auto_execute

| Field | Value |
|-------|-------|
| **Purpose** | Static guard against REPL regression. |
| **Files involved** | `tests/test_titan_repl.py` (new), `core/titan.py` |
| **Dependencies** | P1-070 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Test reads `core/titan.py` and asserts `"auto_execute"` not present.

**Verification checklist:**
- [ ] Test passes

**Rollback strategy:** Delete test.

---

## Track G — P0 Bug Fixes

### P1-080 — TaskEvaluator: remove false-positive keywords

| Field | Value |
|-------|-------|
| **Purpose** | Stop mission corruption on common words (`continue`, `fait`, `done`, bare `terminé`). |
| **Files involved** | `brain/task_evaluator.py` |
| **Dependencies** | P1-016, P1-002 (backup data) |
| **Difficulty** | Medium |
| **Risk** | High |

**Expected result:** Remove or narrow:
- `"continue"`, `"avance"`, `"prochaine étape"` as automatic completion
- `"fait"`, `"done"`, `"terminé"`, `"complété"` as substring matches (too broad)

**Keep explicit phrases:**
- `"étape terminée"`, `"step completed"`, optionally `"étape suivante confirmée"` (document chosen list)

**Verification checklist:**
- [ ] `tests/test_task_evaluator.py` updated: `"continue"` → False
- [ ] `"étape terminée"` → True
- [ ] `"done"` alone → False
- [ ] All TaskEvaluator tests pass

**Rollback strategy:** Restore prior keyword list; restore mission JSON from backup.

---

### P1-081 — TaskEvaluator: require mission active before completion

| Field | Value |
|-------|-------|
| **Purpose** | Prevent step completion when no active mission. |
| **Files involved** | `brain/task_evaluator.py` |
| **Dependencies** | P1-080 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Early return `False` if `not mission.get("active")`.

**Verification checklist:**
- [ ] Test: inactive mission + `"étape terminée"` → False
- [ ] Active mission + explicit phrase → True

**Rollback strategy:** Revert guard clause.

---

### P1-082 — TaskEvaluator: document completion keyword policy in docstring

| Field | Value |
|-------|-------|
| **Purpose** | Phase 8 will replace with structured evaluator; document interim rules. |
| **Files involved** | `brain/task_evaluator.py` |
| **Dependencies** | P1-080 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Class docstring explains explicit-phrase-only policy and Phase 8 upgrade path.

**Verification checklist:**
- [ ] Docstring present

**Rollback strategy:** N/A.

---

### P1-090 — MissionManager: add `should_create_mission_from_message(message)` gate

| Field | Value |
|-------|-------|
| **Purpose** | Separate detection from creation; minimal Phase 1 gating before Phase 8 commands. |
| **Files involved** | `core/mission_manager.py` |
| **Dependencies** | P1-015 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** New method returns `True` only when message contains explicit mission intent, e.g.:
- Prefix commands: `nouvelle mission`, `new mission`, `/mission`
- OR strong keywords: `créer une mission`, `lancer une mission`
- NOT bare `titan`, `projet`, `trading` in casual chat (narrow from current behavior)

**Document chosen rules in method docstring.**

**Verification checklist:**
- [ ] Unit tests for gate method ≥ 6 cases
- [ ] `"bonjour"` → False
- [ ] `"nouvelle mission trading"` → True

**Rollback strategy:** Revert method; Brain always calls old path.

---

### P1-091 — Brain: use mission creation gate

| Field | Value |
|-------|-------|
| **Purpose** | Stop auto-mission on every message when inactive (Brain_Audit bug §13.1). |
| **Files involved** | `brain/brain.py` |
| **Dependencies** | P1-090, P1-057 |
| **Difficulty** | Easy |
| **Risk** | Medium |

**Expected result:** Replace unconditional `create_mission_from_message` with:

```python
if not mission["active"] and self.mission_manager.should_create_mission_from_message(message):
    self.mission_manager.create_mission_from_message(message)
```

**Verification checklist:**
- [ ] `"bonjour"` with inactive mission leaves `active=False`
- [ ] Explicit mission phrase creates mission
- [ ] Tests pass

**Rollback strategy:** Restore unconditional create; restore mission JSON from backup.

---

### P1-092 — Test: mission not created on greeting

| Field | Value |
|-------|-------|
| **Purpose** | Regression for mission auto-creation bug. |
| **Files involved** | `tests/test_mission_gating.py` (new) |
| **Dependencies** | P1-091, P1-060 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Integration test with brain fixture: inactive mission + greeting → still inactive.

**Verification checklist:**
- [ ] Test passes
- [ ] Uses tmp_path mission file

**Rollback strategy:** Delete test.

---

### P1-100 — LLM: wrap API call in try/except

| Field | Value |
|-------|-------|
| **Purpose** | Prevent REPL crash on API failure (P0). |
| **Files involved** | `brain/llm.py` |
| **Dependencies** | P1-019 |
| **Difficulty** | Medium |
| **Risk** | Medium |

**Expected result:** `ask()` catches OpenAI/API errors; returns French user message e.g. `"Désolé, je n'ai pas pu contacter le modèle. Réessaie dans un instant."`; logs error at ERROR level without API key.

**Verification checklist:**
- [ ] Manual mock or unit test triggers exception path
- [ ] No exception propagates to REPL from LLM alone

**Rollback strategy:** Revert try/except (not recommended).

---

### P1-101 — LLM: add retry with backoff (max 2 retries)

| Field | Value |
|-------|-------|
| **Purpose** | Rulebook Section 15.5 transient error handling. |
| **Files involved** | `brain/llm.py` |
| **Dependencies** | P1-100 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Retry only on transient errors (rate limit, timeout, connection); max 3 attempts total; exponential backoff 1s, 2s; log retry at WARNING.

**Verification checklist:**
- [ ] Test: mock fails twice then succeeds → returns response
- [ ] Test: mock fails 3 times → French fallback
- [ ] No infinite retry loop

**Rollback strategy:** Remove retry loop; keep single try/except.

---

### P1-102 — Test: LLM error handling with mocked client

| Field | Value |
|-------|-------|
| **Purpose** | Automated P0 LLM error coverage. |
| **Files involved** | `tests/test_llm.py` (new) |
| **Dependencies** | P1-100, P1-101 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Tests patch `OpenAI` or `LLM.client`; no real API calls.

**Verification checklist:**
- [ ] ≥ 3 tests (success, retry success, final failure)
- [ ] All pass

**Rollback strategy:** Delete test file.

---

### P1-110 — Titan REPL: try/except around `brain.think()`

| Field | Value |
|-------|-------|
| **Purpose** | P0 session stability for unexpected Brain exceptions. |
| **Files involved** | `core/titan.py` |
| **Dependencies** | P1-023 (logging) |
| **Difficulty** | Easy |
| **Risk** | Medium |

**Expected result:**

```python
try:
    reponse = self.brain.think(question)
except Exception as exc:
    logger.exception("Brain failure")
    reponse = "Désolé, une erreur interne s'est produite. On peut réessayer."
```

**Verification checklist:**
- [ ] Mock brain raises → REPL continues, French message printed
- [ ] Exception logged with stack trace
- [ ] Session does not exit

**Rollback strategy:** Remove try/except.

---

### P1-111 — Test: REPL survives Brain exception

| Field | Value |
|-------|-------|
| **Purpose** | Automated REPL error boundary test. |
| **Files involved** | `tests/test_titan_error_handling.py` (new) |
| **Dependencies** | P1-110 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Patch Brain.think to raise; simulate one loop iteration; assert graceful string returned.

**Verification checklist:**
- [ ] Test passes without hanging on input (use injected/mock Titan)

**Rollback strategy:** Delete test.

---

### P1-112 — Brain.think: avoid bare exceptions from orchestrator (optional hardening)

| Field | Value |
|-------|-------|
| **Purpose** | Agent failures should not crash entire turn. |
| **Files involved** | `core/task_orchestrator.py` or `brain/brain.py` |
| **Dependencies** | P1-110 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Orchestrator catches agent execute errors; appends error text to results; Brain continues to LLM.

**Verification checklist:**
- [ ] Test: agent raises → think still returns LLM response
- [ ] Error logged

**Rollback strategy:** Revert try/except in orchestrator.

---

## Track H — MemoryFacade Stub (Phase 3 Prep)

### P1-120 — Create `memory/memory_facade.py` stub

| Field | Value |
|-------|-------|
| **Purpose** | Roadmap expected architecture placeholder; Phase 3 expands to full MemoryService. |
| **Files involved** | `memory/memory_facade.py` (new) |
| **Dependencies** | P1-058 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Class `MemoryFacade` wrapping `MemoryManager` (short-term) + `LongTermMemory` with methods:
- `remember_session(note: str) -> None` (delegates to MemoryManager)
- `get_long_term() -> dict` (delegates to LongTermMemory)

No Brain wiring change yet beyond optional reference.

**Verification checklist:**
- [ ] Module imports cleanly
- [ ] Docstring states Phase 3 expansion plan

**Rollback strategy:** Delete file.

---

### P1-121 — Wire MemoryFacade at Titan composition root

| Field | Value |
|-------|-------|
| **Purpose** | Single entry point ready for Phase 3 without second refactor of Titan. |
| **Files involved** | `core/titan.py`, `memory/memory_facade.py` |
| **Dependencies** | P1-120 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `self.memory = MemoryFacade(short_term=MemoryManager(), long_term=self.long_memory)` or equivalent; Brain still uses injected `LongTermMemory` directly in Phase 1 (no Brain change required).

**Verification checklist:**
- [ ] Startup short-term remember still works
- [ ] No duplicate LongTermMemory instance introduced

**Rollback strategy:** Revert Titan to `MemoryManager()` only.

---

### P1-122 — Test: MemoryFacade delegation smoke

| Field | Value |
|-------|-------|
| **Purpose** | Minimal coverage for stub. |
| **Files involved** | `tests/test_memory_facade.py` (new) |
| **Dependencies** | P1-120 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** ≥ 2 tests for delegation methods.

**Verification checklist:**
- [ ] Tests pass

**Rollback strategy:** Delete test.

---

## Track I — Logging Migration (Modified Files Only)

### P1-130 — Replace prints in `core/titan.py` with logger

| Field | Value |
|-------|-------|
| **Purpose** | Rulebook: no new permanent prints in core paths; Phase 1 DoD. |
| **Files involved** | `core/titan.py` |
| **Dependencies** | P1-023, P1-110 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** User-facing greeting and response prints remain; diagnostic prints move to `logger.debug` gated by `DEBUG_BRAIN` where applicable.

**Verification checklist:**
- [ ] Normal mode REPL UX unchanged for user
- [ ] `TITAN_DEBUG_BRAIN=true` shows extra debug in log file
- [ ] No secrets logged

**Rollback strategy:** Revert logging calls.

---

### P1-131 — Replace prints in `brain/brain.py` with logger

| Field | Value |
|-------|-------|
| **Purpose** | Brain is highest-volume print source; migrate to DEBUG level. |
| **Files involved** | `brain/brain.py` |
| **Dependencies** | P1-023, P1-022 |
| **Difficulty** | Medium |
| **Risk** | Low |

**Expected result:** Pipeline diagnostic prints → `logger.debug`; user still sees only Titan response from REPL.

**Verification checklist:**
- [ ] Default run: console cleaner than before (optional improvement)
- [ ] Debug flag enables detailed pipeline log in file
- [ ] LLM call logged at INFO (without prompt content at DEBUG only if sensitive)

**Rollback strategy:** Revert to prints.

---

### P1-132 — Replace prints in `core/task_orchestrator.py` with logger

| Field | Value |
|-------|-------|
| **Purpose** | Orchestrator prints every turn; migrate to structured logging. |
| **Files involved** | `core/task_orchestrator.py` |
| **Dependencies** | P1-023 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Orchestrator banner and agent progress at DEBUG/INFO.

**Verification checklist:**
- [ ] Orchestration still runs
- [ ] Logs appear in `logs/titan.log`

**Rollback strategy:** Revert prints.

---

## Track J — Release Hygiene

### P1-140 — Bump VERSION to 0.1.0

| Field | Value |
|-------|-------|
| **Purpose** | Mark foundation release per roadmap version mapping. |
| **Files involved** | `config/settings.py` |
| **Dependencies** | P1-150 prerequisites nearly complete |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `VERSION = "0.1.0"`.

**Verification checklist:**
- [ ] Startup banner shows v0.1.0

**Rollback strategy:** Revert version string.

---

### P1-141 — Complete CHANGELOG v0.1.0 entry

| Field | Value |
|-------|-------|
| **Purpose** | Document all Phase 1 architectural changes and P0 fixes. |
| **Files involved** | `CHANGELOG.md` |
| **Dependencies** | All prior tasks |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** `[0.1.0] - YYYY-MM-DD` section listing: DI, single agent path, dead module removal, TaskEvaluator fix, mission gating, error handling, logging, tests.

**Verification checklist:**
- [ ] P0 items from Brain_Audit referenced
- [ ] Migration note: backup mission JSON if upgrading from 0.0.1

**Rollback strategy:** Edit changelog.

---

### P1-142 — Update Titan_Blueprint.md "État actuel" section (minimal)

| Field | Value |
|-------|-------|
| **Purpose** | Keep product doc aligned with v0.1.0 foundation. |
| **Files involved** | `Titan_Blueprint.md` |
| **Dependencies** | P1-141 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Version 0.1.0; list completed foundation items (DI, tests, logging, P0 fixes).

**Verification checklist:**
- [ ] Accurate vs implementation
- [ ] No overclaiming Phase 2+ features

**Rollback strategy:** Revert blueprint section.

---

## Track K — Phase Sign-Off

### P1-150 — Full test suite gate: ≥ 15 tests passing

| Field | Value |
|-------|-------|
| **Purpose** | Roadmap Phase 1 definition of done. |
| **Files involved** | All `tests/` |
| **Dependencies** | All test-producing tasks |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected test inventory (minimum 15):**

| File | Approx tests |
|------|----------------|
| `test_imports.py` | 1+ |
| `test_state_manager.py` | 3+ |
| `test_mission_manager.py` | 4+ |
| `test_task_evaluator.py` | 5+ |
| `test_memory_retriever.py` | 3+ |
| `test_agent_selector.py` | 5+ |
| `test_composition.py` | 2+ |
| `test_single_agent_path.py` | 1+ |
| `test_mission_gating.py` | 1+ |
| `test_llm.py` | 3+ |
| `test_logging_config.py` | 1+ |
| `test_no_dead_modules.py` | 1+ |

**Verification checklist:**
- [ ] `pytest tests/ -v` all pass
- [ ] Count ≥ 15
- [ ] No test writes to real `data/`

**Rollback strategy:** Fix failing tests before sign-off.

---

### P1-151 — Manual smoke test on Windows

| Field | Value |
|-------|-------|
| **Purpose** | Roadmap requires Nolan environment verification. |
| **Files involved** | None (manual) |
| **Dependencies** | P1-150 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Manual script:**

1. `python main.py` — banner, greeting, prompt appear  
2. Send: `bonjour` — response received; mission stays inactive (check `data/titan_mission.json`)  
3. Send: `continue` — mission step does NOT auto-advance  
4. Send: `exit` — clean shutdown  
5. Check `logs/titan.log` exists and has entries  

**Verification checklist:**
- [ ] All 5 steps recorded in CHANGELOG or sign-off note
- [ ] No unhandled traceback

**Rollback strategy:** N/A.

---

### P1-152 — Grep audit: zero forbidden duplicate constructors

| Field | Value |
|-------|-------|
| **Purpose** | Compare to P1-003 baseline; confirm DI complete. |
| **Files involved** | `brain/brain.py`, entire repo |
| **Dependencies** | P1-059, P1-061 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:**

| Pattern | Allowed locations after Phase 1 |
|---------|--------------------------------|
| `AgentManager()` | `core/titan.py` only |
| `ContextManager()` | `core/titan.py` only |
| `StateManager()` | `core/titan.py` only |
| `MissionManager()` | `core/titan.py` only |
| `LongTermMemory()` | `core/titan.py` only |
| `auto_execute` | Not in `core/titan.py` |

**Verification checklist:**
- [ ] Grep results match table
- [ ] Documented delta from P1-003 baseline

**Rollback strategy:** N/A.

---

### P1-153 — Rulebook debt register update (optional documentation)

| Field | Value |
|-------|-------|
| **Purpose** | Mark resolved items in `.cursor/rules/titan.mdc` Section 26.5 when Nolan approves rulebook edits. |
| **Files involved** | `.cursor/rules/titan.mdc` (optional) |
| **Dependencies** | P1-152 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Note Phase 1 completion against debt items 1, 7 (partial), 9 (partial), 10 (partial).

**Verification checklist:**
- [ ] Only update if explicitly requested in execution chat (rulebook changes are sensitive)

**Rollback strategy:** Revert rulebook edit.

---

### P1-154 — Phase 1 definition of done checklist

| Field | Value |
|-------|-------|
| **Purpose** | Formal sign-off against roadmap. |
| **Files involved** | `CHANGELOG.md` |
| **Dependencies** | P1-150, P1-151, P1-152 |
| **Difficulty** | Easy |
| **Risk** | Low |

**Checklist (all must be checked):**

- [ ] One `AgentManager`, one `ContextManager`, one orchestration path per turn  
- [ ] `Brain.__init__` receives all shared dependencies via constructor injection  
- [ ] Dead modules removed with zero orphan imports  
- [ ] REPL survives LLM and Brain exceptions  
- [ ] TaskEvaluator no longer advances mission on `"continue"` alone  
- [ ] Casual greeting does not create mission  
- [ ] `tests/` exists with ≥15 tests covering P0 fixes  
- [ ] Structured logging replaces prints in modified files  
- [ ] `Brain_Audit.md` P0 items addressed (reference in CHANGELOG)  
- [ ] `python main.py` verified manually on Windows  

**Rollback strategy:** N/A — if any fail, return to relevant task.

---

### P1-155 — Tag release v0.1.0 (optional, user-request only)

| Field | Value |
|-------|-------|
| **Purpose** | Git tag milestone when Nolan requests commit/tag. |
| **Files involved** | Git |
| **Dependencies** | P1-154, user explicit request |
| **Difficulty** | Easy |
| **Risk** | Low |

**Expected result:** Git tag `v0.1.0` on signed-off commit.

**Verification checklist:**
- [ ] User explicitly requested tag
- [ ] Working tree clean
- [ ] Tests pass on tagged commit

**Rollback strategy:** Delete local tag; do not force-push.

---

## Complete Task Order (Quick Reference)

Execute strictly top-to-bottom. **Do not skip gates P1-019, P1-150, P1-154.**

| Order | ID | Summary |
|-------|-----|---------|
| 1 | P1-001 | CHANGELOG scaffold |
| 2 | P1-002 | Data backup procedure |
| 3 | P1-003 | Baseline grep audit |
| 4 | P1-010 | Create tests/ |
| 5 | P1-011 | pytest in requirements |
| 6 | P1-012 | conftest fixtures |
| 7 | P1-013 | test_imports |
| 8 | P1-014 | test_state_manager |
| 9 | P1-015 | test_mission_manager |
| 10 | P1-016 | test_task_evaluator (snapshot) |
| 11 | P1-017 | test_memory_retriever |
| 12 | P1-018 | test_agent_selector |
| 13 | P1-019 | **GATE: ≥10 tests** |
| 14 | P1-020 | logs/ directory |
| 15 | P1-021 | logging_config.py |
| 16 | P1-022 | settings feature flags |
| 17 | P1-023 | wire logging in main.py |
| 18 | P1-024 | test_logging_config |
| 19 | P1-030 | __init__.py packages |
| 20 | P1-031 | .env.example |
| 21 | P1-032 | README setup |
| 22 | P1-033 | pyproject.toml |
| 23 | P1-040 | verify action_manager unused |
| 24 | P1-041 | verify core/context unused |
| 25 | P1-042 | delete action_manager |
| 26 | P1-043 | delete core/context |
| 27 | P1-044 | test_no_dead_modules |
| 28 | P1-050 | Brain constructor contract |
| 29 | P1-051 | inject AgentManager (optional param) |
| 30 | P1-052 | Titan passes AgentManager |
| 31 | P1-053 | test composition AgentManager |
| 32 | P1-054 | inject ContextManager |
| 33 | P1-055 | test composition ContextManager |
| 34 | P1-056 | inject StateManager |
| 35 | P1-057 | inject MissionManager |
| 36 | P1-058 | inject LongTermMemory |
| 37 | P1-059 | remove Brain fallback constructors |
| 38 | P1-060 | brain test factory fixture |
| 39 | P1-061 | test no duplicate constructors in Brain |
| 40 | P1-062 | reorder Titan.__init__ |
| 41 | P1-070 | remove auto_execute from REPL |
| 42 | P1-071 | document self.agents policy |
| 43 | P1-072 | test single agent path |
| 44 | P1-073 | test no auto_execute in titan.py |
| 45 | P1-080 | TaskEvaluator keyword fix |
| 46 | P1-081 | TaskEvaluator requires active mission |
| 47 | P1-082 | TaskEvaluator docstring |
| 48 | P1-090 | mission should_create gate |
| 49 | P1-091 | Brain uses mission gate |
| 50 | P1-092 | test mission gating |
| 51 | P1-100 | LLM try/except |
| 52 | P1-101 | LLM retry backoff |
| 53 | P1-102 | test_llm |
| 54 | P1-110 | REPL try/except |
| 55 | P1-111 | test REPL error handling |
| 56 | P1-112 | orchestrator error hardening (optional) |
| 57 | P1-120 | MemoryFacade stub |
| 58 | P1-121 | wire MemoryFacade in Titan |
| 59 | P1-122 | test_memory_facade |
| 60 | P1-130 | logging migration titan.py |
| 61 | P1-131 | logging migration brain.py |
| 62 | P1-132 | logging migration task_orchestrator.py |
| 63 | P1-140 | VERSION 0.1.0 |
| 64 | P1-141 | CHANGELOG v0.1.0 entry |
| 65 | P1-142 | Blueprint update |
| 66 | P1-150 | **GATE: ≥15 tests** |
| 67 | P1-151 | manual Windows smoke |
| 68 | P1-152 | grep audit sign-off |
| 69 | P1-153 | rulebook update (optional) |
| 70 | P1-154 | **FINAL DoD checklist** |
| 71 | P1-155 | git tag (user request only) |

---

## Suggested Chat Session Groupings

For multi-chat execution without losing context, batch tasks as follows:

| Session | Tasks | Theme |
|---------|-------|-------|
| 1 | P1-001 → P1-019 | Tests scaffold + baseline safety net |
| 2 | P1-020 → P1-033 | Logging + package hygiene |
| 3 | P1-040 → P1-044 | Dead code removal |
| 4 | P1-050 → P1-062 | Full dependency injection |
| 5 | P1-070 → P1-073 | Single agent execution path |
| 6 | P1-080 → P1-092 | TaskEvaluator + mission gating |
| 7 | P1-100 → P1-112 | LLM + REPL error handling |
| 8 | P1-120 → P1-132 | MemoryFacade stub + logging migration |
| 9 | P1-140 → P1-154 | Release + sign-off |

---

## Mapping: Roadmap Objectives → Tasks

| Roadmap Phase 1 Objective | Tasks |
|---------------------------|-------|
| Single composition root + DI | P1-050 → P1-062 |
| Remove double agent execution | P1-070 → P1-073 |
| Retire dead modules | P1-040 → P1-044 |
| TaskEvaluator P0 fix | P1-080 → P1-082, P1-016 |
| Mission auto-create gating | P1-090 → P1-092 |
| REPL + LLM error handling | P1-100 → P1-111 |
| tests/ with pytest | P1-010 → P1-019, P1-150 |
| logs/ with logging | P1-020 → P1-024, P1-130 → P1-132 |
| .env.example, README | P1-031, P1-032 |
| pyproject.toml / PYTHONPATH | P1-033 |
| __init__.py package hygiene | P1-030 |
| MemoryFacade stub | P1-120 → P1-122 |
| Feature flags DEBUG_BRAIN, LOG_LEVEL | P1-022 |

---

## Mapping: Brain Audit P0 → Tasks

| P0 Item | Tasks |
|---------|-------|
| Double agent execution | P1-070 → P1-073 |
| TaskEvaluator false positives | P1-080 → P1-082 |
| No LLM error handling | P1-100 → P1-102 |
| No REPL error wrapper | P1-110 → P1-111 |
| Mission auto-creation on casual messages | P1-090 → P1-092 |
| Duplicate AgentManager (architectural P0) | P1-051 → P1-059, P1-152 |

---

## Out of Scope Reminder (Defer to Later Phases)

| Item | Phase |
|------|-------|
| Use retrieved memory in prompt (not full dump) | 2 |
| Wire identity.py + constitution | 2 |
| User-aware memory writes (Nolan/Ibrahim) | 3 |
| Dynamic context from state/mission | 4 |
| Unified agent routing registry | 5 |
| Conversation history in prompt | 7 |
| Mission step history preservation (no list.remove) | 8 |
| LLM model name in settings.py | 2 or 14 |

---

## Risk Register (Phase 1 Summary)

| Risk | Likelihood | Impact | Mitigation tasks |
|------|------------|--------|------------------|
| DI breaks hot path | Medium | High | P1-019 gate, P1-053–P1-061, incremental injection |
| Mission JSON corrupted in testing | Medium | Medium | P1-002 backup, tmp_path in tests |
| TaskEvaluator fix too aggressive | Low | Medium | Keep explicit phrases; document in P1-082 |
| Mission gate blocks legitimate missions | Medium | Low | Explicit command keywords; tune in P1-090 tests |
| Logging migration hides user output | Low | Low | Keep response prints in REPL; DEBUG only for pipeline |
| Over-scope into Brain redesign | Medium | High | Scope boundary section; review each task against defer list |

---

**End of Phase 1 Implementation Plan**

*Planning document only. No Python code was modified in its creation.*
