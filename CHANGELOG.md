# Changelog

All notable changes to the Titan project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Version policy

- **Semver:** `MAJOR.MINOR.PATCH` — breaking changes, new features, and bug fixes respectively.
- **Current codebase version:** `0.10.0` (see `config/settings.py`).
- **Phase 1 target release:** `0.1.0` — Titan V2 Phase 1 (Architecture Cleanup). **Shipped 2026-06-27.**
- **Phase 10A release:** `0.10.0` — Tool Runtime V2 default. **Shipped 2026-06-28.**
- **Future milestone:** `2.0.0` — full Titan V2 release after all planned phases.

## [Unreleased]

_No changes yet._

## [0.10.0] - 2026-06-28

Titan V3 **Phase 10A — Real Tool Integration Framework** closure release. Tool Runtime V2 is the default execution path; legacy Phase 6 direct-registry dispatch remains available via opt-out.

### Added

- **Tool Runtime Layer (`tools/tool_runtime.py`):** pre-flight gates for health, dependencies, quotas, permissions, and confirmation before execution.
- **Provider framework (`tools/providers/`):** `BaseProvider`, `ProviderRegistry`, version compatibility checks, stub providers for `web_search` and `calendar` (no external APIs).
- **Confirmation gate (`tools/confirmation_gate.py`):** capability-first gating with `/confirm` flow wired through Brain pipeline (`brain/tool_confirmation_handler.py`).
- **Audit logging (`tools/audit/`):** append-only JSONL structured events with params digest (no secrets).
- **Persistence foundation:** `ToolRunStore`, optional metrics/quota snapshots (`TITAN_TOOL_PERSIST_RUNS`, `TITAN_TOOL_PERSIST_METRICS`).
- **Async execution foundation:** thread-pool `AsyncExecutor` with poll/cancel support.
- **Brain integration:** `tool_execution_bridge.py`, provider health in prompts (`SANTÉ OUTILS ET PROVIDERS`), `ExecutionCoordinator` → `ToolDispatcher` → `ToolRuntime`.
- **96 Phase 10A regression tests** across `test_tool_runtime*.py`, `test_confirmation_gate.py`, `test_tool_audit.py`, `test_tool_persistence_async.py`, `test_provider_framework.py`, `test_brain_tool_integration.py`.

### Changed

- **`TITAN_TOOL_RUNTIME_V2` default:** `true` — composition root `ToolManager` uses `ToolRuntime` by default.
- **`VERSION`:** `0.9.0` → `0.10.0`.
- **`ToolManager.run()`:** routes through runtime when v2 enabled; returns `run_id` on outcomes.
- **`.env.example`:** documents Phase 10A tool runtime settings.

### Backward compatibility

- Set `TITAN_TOOL_RUNTIME_V2=false` or `ToolManager(use_runtime_v2=False)` to restore Phase 6 direct-registry path.
- Phase 6 `ToolResult` contract preserved via `outcome_to_result()`.
- External API integrations deferred to Phase 10B; provider stubs only.

## [0.1.0] - 2026-06-27

Titan V2 **Phase 1 — Architecture Cleanup** foundation release. Resolves Brain Audit P0 items (double agent execution, TaskEvaluator false positives, missing REPL/LLM error handling) and establishes a single composition root with regression tests and structured logging.

### Added

- `tests/` scaffold and **110** regression tests: imports, managers, composition/DI guards, single agent path, REPL behavior, TaskEvaluator, mission gating, LLM error handling, REPL error handling, orchestrator hardening, logging, dead-module guards, `MemoryFacade`.
- `logs/` directory and `core/logging_config.py` — rotating file + console handlers (`P1-020`–`P1-024`).
- `LOG_LEVEL`, `LOG_DIR`, `DEBUG_BRAIN` feature flags in `config/settings.py` (`P1-022`).
- Package `__init__.py` files for all seven top-level packages (`P1-030`).
- `.env.example`, `README.md` (Windows setup/run/test), `pyproject.toml` pytest config (`P1-031`–`P1-033`).
- `tests/conftest.py` `brain` fixture with mocked LLM and temp JSON paths (`P1-060`).
- `memory/memory_facade.py` stub wired at composition root (`P1-120`–`P1-122`).
- Phase 1 data backup procedure (`data/backups/YYYYMMDD/`) documented below for manual testing.

### Changed

- **Dependency injection (Track E, `P1-050`–`P1-062`):** `Brain` requires keyword-injected shared managers from `Titan`; one instance each of `AgentManager`, `ContextManager`, `StateManager`, `MissionManager`, `LongTermMemory`.
- **Single agent orchestration path (Track F, `P1-070`–`P1-073`):** `Titan.start()` no longer calls `AgentManager.auto_execute()`. Agent work runs only via `Brain.think()` → `TaskOrchestrator.orchestrate()`.
- **TaskEvaluator (Track G, `P1-080`–`P1-082`):** mission steps advance only on explicit completion phrases when a mission is active. Casual words like `continue`, `done`, and bare `fait`/`terminé` no longer corrupt mission progress.
- **Mission gating (`P1-090`–`P1-092`):** missions created only on explicit intent (`nouvelle mission`, `créer une mission`, etc.). Greetings and casual keyword mentions no longer auto-start missions.
- **LLM error handling (`P1-100`–`P1-102`):** `LLM.ask()` catches API failures, retries transient errors (max 3 attempts, backoff), returns a French fallback message; never raises to callers.
- **REPL error handling (`P1-110`–`P1-112`):** `Titan.start()` wraps `brain.think()` in try/except; session continues after internal failures; orchestrator agent errors are logged and do not abort the turn.
- **Logging migration (`P1-130`–`P1-132`):** `print()` debug replaced with `logging` in `core/titan.py`, `brain/brain.py`, and `core/task_orchestrator.py` (guarded by `DEBUG_BRAIN` where applicable).

### Removed

- `core/action_manager.py` (`P1-042`) — unwired placeholder; Brain uses `TaskOrchestrator` / agents instead.
- `core/context.py` (`P1-043`) — duplicate legacy context; active context is `context/context_manager.py`.

### Fixed — Brain Audit P0

| P0 item | Resolution |
|---------|------------|
| Double agent execution (TD-1) | Single path: `Brain.think()` → `TaskOrchestrator` only (`P1-070`–`P1-073`) |
| TaskEvaluator false positives | Explicit-phrase-only completion policy; inactive-mission guard (`P1-080`–`P1-082`) |
| No REPL + LLM error handling | `LLM.ask()` try/retry/fallback (`P1-100`–`P1-102`); REPL try/except (`P1-110`–`P1-111`) |

### Migration — upgrading from 0.0.1

Before running `0.1.0` against live runtime data, **back up** `data/titan_mission.json`, `data/titan_state.json`, and `data/long_term_memory.json`. Mission gating and TaskEvaluator fixes change when missions are created and when steps advance; existing mission JSON from `0.0.1` may behave differently under the new rules.

See **Phase 1 testing — data backup procedure** below for PowerShell/Bash copy and restore steps.

---
### Phase 1 testing — data backup procedure (P1-002)

Before **manual testing** of tasks **P1-080 and later** (TaskEvaluator, mission gating, and related Brain changes), back up live runtime JSON so mission and memory state can be restored if a test corrupts or resets files.

#### When to back up

- Before the first manual REPL or integration test session for **P1-080+**
- Before any experiment that runs `python main.py` against real `data/` files after mission-gating or TaskEvaluator code changes
- Automated tests must use temporary directories (`tmp_path` / injected paths) and **must not** rely on this procedure — see P1-010+

#### Files to back up

Copy these three files from `data/`:

| File | Purpose |
|------|---------|
| `data/titan_mission.json` | Active mission and step progress |
| `data/titan_state.json` | Operational session/project state |
| `data/long_term_memory.json` | Durable user notes (Nolan / Ibrahim — sensitive) |

Do not commit backup contents or paste personal notes into the changelog.

#### Backup directory convention

Use a dated folder under `data/backups/`:

```text
data/backups/YYYYMMDD/
├── titan_mission.json
├── titan_state.json
└── long_term_memory.json
```

Replace `YYYYMMDD` with the backup date (e.g. `20260623` for 23 June 2026). One folder per backup session; create a new dated folder before each risky manual test run if you need a fresh restore point.

#### Backup steps

**PowerShell (Windows — project root):**

```powershell
$date = Get-Date -Format "yyyyMMdd"
$dest = "data/backups/$date"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item "data/titan_mission.json" $dest
Copy-Item "data/titan_state.json" $dest
Copy-Item "data/long_term_memory.json" $dest
Write-Host "Backup written to $dest"
```

**Bash (Linux / macOS — project root):**

```bash
DATE=$(date +%Y%m%d)
DEST="data/backups/${DATE}"
mkdir -p "$DEST"
cp data/titan_mission.json data/titan_state.json data/long_term_memory.json "$DEST"
echo "Backup written to $DEST"
```

#### Restore steps

If manual testing corrupts or unwantedly resets runtime data, restore from the chosen backup folder (replace `YYYYMMDD` with the backup date):

**PowerShell (Windows):**

```powershell
$src = "data/backups/YYYYMMDD"
Copy-Item "$src/titan_mission.json" "data/titan_mission.json" -Force
Copy-Item "$src/titan_state.json" "data/titan_state.json" -Force
Copy-Item "$src/long_term_memory.json" "data/long_term_memory.json" -Force
Write-Host "Restored from $src"
```

**Bash:**

```bash
SRC="data/backups/YYYYMMDD"
cp "$SRC/titan_mission.json" data/titan_mission.json
cp "$SRC/titan_state.json" data/titan_state.json
cp "$SRC/long_term_memory.json" data/long_term_memory.json
echo "Restored from $SRC"
```

Verify restore: start Titan (`python main.py`) and confirm mission step, state, and memory match expectations before continuing Phase 1 testing.

#### Rollback of this procedure

Documentation only — remove or edit this section in `CHANGELOG.md` if the process changes in a later phase.

### Phase 1 baseline — manager instantiation audit (P1-003)

**Date:** 2026-06-23  
**Purpose:** Capture pre-Phase-1 duplicate instantiation locations before dependency injection (Track E, P1-050+). Used to verify P1-152 grep sign-off: after DI, each manager class should instantiate only in `core/titan.py`.

**Grep patterns run (repo root, all files):**

```text
AgentManager\(
ContextManager\(
StateManager\(
MissionManager\(
LongTermMemory\(
```

**Production Python instantiations (`*.py` only — authoritative baseline):**

| Manager | File | Line | Attribute |
|---------|------|------|-----------|
| `ContextManager()` | `core/titan.py` | 24 | `self.context` |
| `ContextManager()` | `brain/brain.py` | 35 | `self.context_manager` |
| `AgentManager()` | `core/titan.py` | 26 | `self.agents` |
| `AgentManager()` | `brain/brain.py` | 40 | `self.agent_manager` |
| `LongTermMemory()` | `brain/brain.py` | 36 | `self.long_memory` |
| `StateManager()` | `brain/brain.py` | 46 | `self.state_manager` |
| `MissionManager()` | `brain/brain.py` | 47 | `self.mission_manager` |

**Summary counts (production `*.py`):**

| Pattern | Total | `core/titan.py` | `brain/brain.py` | Other `.py` |
|---------|-------|-----------------|------------------|-------------|
| `ContextManager()` | 2 | 1 | 1 | 0 |
| `AgentManager()` | 2 | 1 | 1 | 0 |
| `LongTermMemory()` | 1 | 0 | 1 | 0 |
| `StateManager()` | 1 | 0 | 1 | 0 |
| `MissionManager()` | 1 | 0 | 1 | 0 |

**Known duplicates (pre-DI):**

- `ContextManager` — Titan and Brain each construct one (2 instances per process).
- `AgentManager` — Titan and Brain each construct one (2 instances per process; Brain also wires `TaskManager` / `TaskOrchestrator` against its own copy).

**Titan-only today:** `ContextManager`, `AgentManager` (Brain additionally owns `StateManager`, `MissionManager`, `LongTermMemory` — not yet constructed in Titan).

**Non-code matches (documentation only — not runtime instantiations):**

- `Phase1_Implementation_Plan.md`, `Titan_V2_Roadmap.md`, `.cursor/rules/titan.mdc` — describe target state or examples; no executable calls.

**Target state (P1-152 sign-off):**

| Pattern | Expected location after DI |
|---------|----------------------------|
| `AgentManager()` | `core/titan.py` only |
| `ContextManager()` | `core/titan.py` only |
| `StateManager()` | `core/titan.py` only |
| `MissionManager()` | `core/titan.py` only |
| `LongTermMemory()` | `core/titan.py` only |

**Verification checklist (P1-003):**

- [x] Grep run: `AgentManager\(`, `ContextManager\(`, `StateManager\(`, `MissionManager\(`, `LongTermMemory\(`
- [x] Results recorded for comparison at P1-152

#### Rollback of this audit

Documentation only — delete or edit this section in `CHANGELOG.md` if the baseline must be re-captured.

### Phase 1 gate — full test suite (P1-150)

**Date:** 2026-06-27  
**Purpose:** Roadmap Phase 1 definition of done — minimum 15 passing tests; no writes to live `data/`.

**Command run (project root):**

```text
python -m pytest tests/ -v
```

**Result (2026-06-27):**

| Metric | Count |
|--------|-------|
| Tests collected | 110 |
| Passed | 110 |
| Failed | 0 |

**Gate threshold:** ≥ 15 passing tests; all pass; no test writes to real `data/`. **Gate status: PASS.**

**Test inventory by file:**

| File | Tests collected |
|------|-----------------|
| `tests/test_imports.py` | 36 |
| `tests/test_state_manager.py` | 3 |
| `tests/test_mission_manager.py` | 16 |
| `tests/test_task_evaluator.py` | 19 |
| `tests/test_memory_retriever.py` | 5 |
| `tests/test_agent_selector.py` | 5 |
| `tests/test_composition.py` | 9 |
| `tests/test_single_agent_path.py` | 1 |
| `tests/test_mission_gating.py` | 2 |
| `tests/test_llm.py` | 4 |
| `tests/test_logging_config.py` | 1 |
| `tests/test_no_dead_modules.py` | 2 |
| `tests/test_titan_repl.py` | 1 |
| `tests/test_titan_error_handling.py` | 2 |
| `tests/test_orchestrator_errors.py` | 2 |
| `tests/test_memory_facade.py` | 3 |

**Verification checklist (P1-150):**

- [x] `pytest tests/ -v` all pass
- [x] Count ≥ 15 (110 collected)
- [x] No test writes to real `data/` (fixtures use `tmp_path` / injected paths)

### Phase 1 sign-off — manual Windows smoke test (P1-151)

**Date:** 2026-06-27  
**Environment:** Windows 10, Python 3.14, project root  
**Procedure:** Mission JSON backed up to `data/backups/20260627/`; inactive mission seeded; `python main.py` with piped input `bonjour` → `continue` → `exit`; mission restored from backup after test.

| Step | Expected | Result |
|------|----------|--------|
| 1. Startup | Banner `Titan AI v0.1.0`, greeting, `Toi :` prompt | PASS |
| 2. `bonjour` | Response received; mission stays inactive | PASS |
| 3. `continue` | Mission step does not auto-advance | PASS |
| 4. `exit` | Clean shutdown message | PASS |
| 5. `logs/titan.log` | File exists with entries | PASS |

**Additional checks:** No unhandled traceback in session output.

**Verification checklist (P1-151):**

- [x] All 5 steps recorded
- [x] No unhandled traceback

### Phase 1 sign-off — DI grep audit (P1-152)

**Date:** 2026-06-27  
**Purpose:** Confirm duplicate manager constructors eliminated vs P1-003 baseline.

**Production instantiations (`*.py` excluding `tests/`):**

| Pattern | Location | Line | Notes |
|---------|----------|------|-------|
| `AgentManager()` | `core/titan.py` | 32 | Composition root |
| `ContextManager()` | `core/titan.py` | 33 | Composition root |
| `StateManager()` | `core/titan.py` | 34 | Composition root |
| `MissionManager()` | `core/titan.py` | 35 | Composition root |
| `LongTermMemory()` | `core/titan.py` | 36 | Composition root |

**`auto_execute`:** Not present in `core/titan.py`. Method remains on `AgentManager` for legacy API; REPL uses Brain orchestrator only (`tests/test_titan_repl.py` guard).

**Delta from P1-003 baseline:**

| Manager | Pre-DI (P1-003) | Post-DI (P1-152) |
|---------|-----------------|------------------|
| `ContextManager()` | 2 (`titan.py`, `brain.py` impl) | 1 (`titan.py` only; `brain.py` docstring examples excluded) |
| `AgentManager()` | 2 (`titan.py`, `brain.py` impl) | 1 (`titan.py` only) |
| `LongTermMemory()` | 1 (`brain.py` impl) | 1 (`titan.py` only) |
| `StateManager()` | 1 (`brain.py` impl) | 1 (`titan.py` only) |
| `MissionManager()` | 1 (`brain.py` impl) | 1 (`titan.py` only) |

**Verification checklist (P1-152):**

- [x] Grep results match allowed-locations table
- [x] Delta from P1-003 baseline documented

### Phase 1 definition of done (P1-154)

**Date:** 2026-06-27  
**Sign-off:** Titan V2 Phase 1 (Architecture Cleanup) — **COMPLETE**

| Criterion | Status | Evidence |
|-----------|--------|----------|
| One `AgentManager`, one `ContextManager`, one orchestration path per turn | PASS | P1-052–P1-058, P1-070–P1-073, P1-152 |
| `Brain.__init__` receives all shared dependencies via constructor injection | PASS | P1-059, `tests/test_composition.py` |
| Dead modules removed with zero orphan imports | PASS | P1-042–P1-044 |
| REPL survives LLM and Brain exceptions | PASS | P1-100–P1-111, `tests/test_titan_error_handling.py` |
| TaskEvaluator no longer advances mission on `"continue"` alone | PASS | P1-080–P1-082, `tests/test_task_evaluator.py` |
| Casual greeting does not create mission | PASS | P1-090–P1-092, P1-151 step 2 |
| `tests/` exists with ≥15 tests covering P0 fixes | PASS | P1-150 — 110 tests |
| Structured logging replaces prints in modified files | PASS | P1-020–P1-024, P1-130–P1-132 |
| `Brain_Audit.md` P0 items addressed | PASS | See **Fixed — Brain Audit P0** above |
| `python main.py` verified manually on Windows | PASS | P1-151 |

**Verification checklist (P1-154):**

- [x] All criteria checked and passing

### Phase 1 gate — baseline test count (P1-019)

**Date:** 2026-06-24  
**Purpose:** Gate before Track E dependency injection (P1-050+). Do not refactor wiring without this test safety net.

**Command run (project root):**

```text
pytest tests/ -v
```

**Result (2026-06-24):**

| Metric | Count |
|--------|-------|
| Tests collected | 71 |
| Passed | 64 |
| Xfailed (documented P0 — P1-016 TaskEvaluator) | 7 |
| Failed | 0 |

**Gate threshold:** ≥ 10 passing tests (xfail allowed for documented P0 cases). **Gate status: PASS** — 64 passed; Track E (DI) may proceed.

**Test inventory by file:**

| File | Tests collected | Notes |
|------|-----------------|-------|
| `tests/test_imports.py` | 36 | Production module import smoke (P1-013) |
| `tests/test_state_manager.py` | 3 | Load/save round-trip (P1-014) |
| `tests/test_mission_manager.py` | 6 | Mission lifecycle (P1-015) |
| `tests/test_task_evaluator.py` | 16 | 9 pass + 7 xfail snapshot (P1-016) |
| `tests/test_memory_retriever.py` | 5 | Keyword relevance (P1-017) |
| `tests/test_agent_selector.py` | 5 | Routing smoke (P1-018) |

**Xfail documentation:** Seven cases in `tests/test_task_evaluator.py` assert desired post-P1-080 behavior (`continue`, `fait`, `done`, etc. must not complete steps). Marked `# P0: must become False in P1-080`; expected to flip to pass when P1-080 lands.

**Verification checklist (P1-019):**

- [x] Full suite green (64 passed, 7 xfail documented, 0 failed)
- [x] Test count recorded in CHANGELOG

#### Rollback of this gate

Documentation only — re-run `pytest tests/ -v` after any test changes to refresh counts in this section.

### Phase 1 deletion gates — dead module import verification (P1-040, P1-041)

**Date:** 2026-06-27  
**Purpose:** Confirm safe deletion gates before / after removing `core/action_manager.py` and `core/context.py`.

**Grep patterns (all `*.py` under repo root):**

```text
from core.action_manager
import action_manager
from core.context
from core import context
```

**Result:** No production Python imports found. Modules deleted in P1-042 / P1-043; guarded by `tests/test_no_dead_modules.py` (P1-044).

**Verification checklist (P1-040, P1-041):**

- [x] Grep empty for production imports of `core/action_manager`
- [x] Grep empty for production imports of `core/context`
- [x] Documented in CHANGELOG
