# Proposal: PoB2 Engine Reliability and Equipment Verdict Consolidation

## Why

The PoB2 headless calculation engine and equipment evaluation paths currently suffer from two reliability flaws:
1. `PobEngine.call()` in `path-of-building-2-mcp` reads engine stdout with an unbounded blocking `readline()`, ignoring `call_timeout=60`. If Lua hangs or enters an infinite loop, the engine lock is held forever, stalling all future simulations. Furthermore, if the engine process dies, `Pob2EquipmentSession` in `poe2-companion` swallows the error without auto-recovery, and baseline restoration in `finally` blocks silently suppresses exceptions via `except Exception: pass`.
2. Equipment verdict merging in `companion/dashboard_api.py` is inconsistent: the weapon and ring paths treat tactical advice as veto-only (`REJECT` overrides, otherwise policy stands), whereas generic slots directly assign `final_verdict = tactical.verdict.value`, allowing tactical advice to inappropriately override policy verdicts with `EQUIP_NOW`.

Addressing these issues ensures predictable IPC timeouts with process self-healing and consistent, explainable equipment recommendations across all slots.

## What Changes

- **Engine Call Timeout Enforcement (Windows-Compatible)**: Replace unbounded `readline()` in `PobEngine.call()` with a reader thread and `queue.Queue(timeout=call_timeout)` that works safely across Windows and Linux (no `select` on pipes). On timeout, forcefully terminate the subprocess, clean up state, release the engine lock, and raise `EngineTimeoutError` (inheriting from `EngineError`).
- **Engine Process Recovery**: Add `restart()` and `ensure_alive()` methods to `PobEngine` that safely restart dead or timed-out processes and await the `MCP_ENTRY_READY` sentinel while respecting the engine lock.
- **Session Health Tracking and Auto-Recovery**:
  - Add an `is_healthy` state flag and `unhealthy_reason` to `Pob2EquipmentSession`.
  - When any `EngineError` occurs, mark session `unhealthy`.
  - On the subsequent simulation call, attempt a single restart and re-import `self.xml` into the fresh engine before proceeding. Do not automatically retry the call that originally triggered the failure.
  - In baseline restore `finally` blocks, replace `except Exception: pass` with warning logs (`logging.getLogger(__name__).warning(...)`) and mark the session `unhealthy` if restore fails.
- **Engine Health Reporting in `/api/status`**: Expose engine health in the `/api/status` response dictionary (both via `engine_status` object and `status.engine_healthy`).
- **Unified Verdict Merge Rule (`merge_verdicts`)**:
  - Research confirms that generic slot override behavior was an unintentional divergence in commit `3256cf6`.
  - Establish a single canonical `merge_verdicts(policy_verdict, tactical_verdict)` function in `companion.equipment.tactical_advisor` enforcing strict **veto-only** semantics: tactical advice may only veto with `REJECT`; otherwise the policy verdict (`EQUIP_NOW`, `CONDITIONAL_UPGRADE`, `REJECT`) is preserved.
  - Apply `merge_verdicts()` across weapon, ring, and generic slot paths in `companion/dashboard_api.py`.
  - Provide a complete test matrix covering all 9 verdict pairs (`EQUIP_NOW`, `CONDITIONAL_UPGRADE`, `REJECT`) across all three evaluation paths.

## Capabilities

### New Capabilities
- `pob2-engine-recovery`: Enforces real `call_timeout` via a cross-platform reader queue in `PobEngine`, kills timed-out engine processes, provides `restart()` / `ensure_alive()`, tracks `is_healthy` in `Pob2EquipmentSession`, logs failed baseline restorations, and surfaces engine health in `/api/status`.
- `equipment-verdict-consolidation`: Unifies verdict merging logic across weapon, ring, and generic equipment paths in `companion/dashboard_api.py` using `merge_verdicts()`, standardizing on veto-only tactical evaluation.

### Modified Capabilities
<!-- None -->

## Impact

- `path-of-building-2-mcp`:
  - `server/pob_mcp/engine.py`: `import time`, `EngineTimeoutError`, reader thread + `queue.Queue`, `restart()`, `ensure_alive()`.
  - Unit tests for timeout, error recovery, and restart semantics.
- `poe2-companion`:
  - `companion/equipment/pob2_equipment_advisor.py`: `is_healthy` flag, single-restart recovery on subsequent call, `finally` baseline restore logging and health degradation.
  - `companion/equipment/tactical_advisor.py`: `merge_verdicts(policy_verdict, tactical_verdict)` helper.
  - `companion/dashboard_api.py`: unified use of `merge_verdicts()` in weapon, ring, and generic slot branches; health status in `get_dashboard_status`.
  - `companion/dashboard_server.py`: engine health propagation in `/api/status`.
  - Tests: comprehensive 3x9 verdict matrix tests, session recovery tests, timeout simulation tests.
