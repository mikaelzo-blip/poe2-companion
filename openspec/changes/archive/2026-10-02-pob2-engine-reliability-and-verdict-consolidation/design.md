# Design: PoB2 Engine Reliability and Equipment Verdict Consolidation

## Context

The companion evaluates equipment using two tiers: mathematical/policy evaluation (`evaluate_fubgun_equipment_policy`, `evaluate_fubgun_weapon_policy`, `evaluate_dual_ring_policy`) and situational tactical advice (`generate_tactical_advice`). The mathematical engine runs as a persistent headless Lua process in `path-of-building-2-mcp` communicating over JSON lines.

As detailed in `proposal.md`, two vulnerabilities exist:
1. `PobEngine.call()` relies on synchronous `readline()` without a real timeout. On Windows, pipe `select()` is unsupported, causing Lua deadlocks to hold `_lock` indefinitely. Session error handling silently suppresses restore failures with `pass` and does not recover from dead engine processes.
2. In `companion/dashboard_api.py`, the generic slot branch directly assigns `final_verdict = tactical.verdict.value`, creating divergent behavior where tactical advice can promote a policy `CONDITIONAL_UPGRADE` or `REJECT` to `EQUIP_NOW`, whereas weapon and ring branches restrict tactical advice to a veto (`REJECT`).

## Goals / Non-Goals

**Goals:**
- Provide a robust, cross-platform (Windows & Linux compatible) timeout mechanism in `PobEngine.call()` that enforces `call_timeout` without `select`.
- On timeout, terminate the offending process, release synchronization locks, and raise `EngineTimeoutError` (inheriting from `EngineError`).
- Provide `restart()` and `ensure_alive()` on `PobEngine` to safely recreate the process and re-establish the `MCP_ENTRY_READY` protocol.
- Introduce `is_healthy` tracking in `Pob2EquipmentSession`, degrade health on `EngineError`, and attempt a single restart + baseline XML re-import on the subsequent invocation without auto-retrying the failed simulation.
- Log failures during baseline XML restoration in `finally` blocks and degrade session health if restoration fails.
- Expose engine health in `/api/status` responses.
- Implement a canonical `merge_verdicts(policy_verdict, tactical_verdict)` function in `companion.equipment.tactical_advisor` enforcing veto-only tactical evaluation across all three equipment paths (`weapon`, `ring`, `generic_slot`).
- Implement an automated 3x9 test matrix testing all combinations of `(policy x tactical)` verdicts across all three paths.

**Non-Goals:**
- Introducing SSE or WebSockets for status or clipboard streaming.
- Migrating `dashboard_server.py` to FastAPI or async frameworks.
- Ephemeral or snapshot PoB2 sessions.
- Touching or modifying `oauth_status.json`, contents of `runtime/`, or credential files.

## Decisions

### 1. Cross-Platform Engine Timeout via Reader Thread + Queue
- **Decision**: In `PobEngine`, spawn a background worker thread (`daemon=True`) to read lines from `stdout` and place them into a `queue.Queue()`. In `call()`, retrieve responses with `self._stdout_queue.get(timeout=self.call_timeout)`.
- **Rationale**: On Windows, anonymous pipes created by `subprocess.Popen` are OS file handles, not winsock sockets. Calling `select.select()` on them raises `OSError: [WinError 10038]`. `queue.Queue` with timeout is supported natively on all Python platforms and avoids platform-specific C extensions or `ctypes` Win32 overlapped I/O.
- **Alternatives Considered**:
  - `select.select()`: Fails immediately on Windows with `OSError`.
  - Polling with `time.sleep()` and `proc.poll()`: Does not provide byte-level line buffering and wastes CPU cycles.

### 2. Timeout Exception Hierarchy and Process Cleanup
- **Decision**: Define `class EngineTimeoutError(EngineError): pass`. On `queue.Empty`:
  1. Call `self.close()` (which forcefully kills `self._proc` via `kill()`).
  2. Clear the stdout reader queue.
  3. Release `self._lock` (guaranteed via `try...finally` or exiting the lock context).
  4. Raise `EngineTimeoutError(f"PoB2 engine command '{cmd}' timed out after {self.call_timeout}s")`.
- **Rationale**: Callers already catching `EngineError` will catch timeouts safely, while callers needing timeout-specific recovery or telemetry can catch `EngineTimeoutError` explicitly.

### 3. Restart and Ensure Alive Lifecycle
- **Decision**: Implement `restart()` and `ensure_alive()` on `PobEngine`:
  - `restart()`: Acquires `_lock`, closes existing process (killing if needed), resets state (`_ready.clear()`, drains queues), and calls `self.start()` to launch Docker/Lua and await `MCP_ENTRY_READY`.
  - `ensure_alive()`: Acquires `_lock`. If `self._proc` is None or `self._proc.poll() is not None`, calls `restart()`. If already alive, returns immediately.
- **Rationale**: Keeps lock semantics intact and prevents two threads from racing to restart a dead engine.

### 4. Session Health State & Lazy Recovery
- **Decision**: Add `self.is_healthy: bool = True` and `self.unhealthy_reason: str | None = None` to `Pob2EquipmentSession`.
  - When any `EngineError` occurs during `simulate_item`, `simulate_weapon_plan`, or `simulate_ring_candidate`:
    - Set `self.is_healthy = False`.
    - Set `self.unhealthy_reason = str(exc)`.
    - Discard the candidate and return `None` (no automatic retry of the failed item).
  - At the start of any simulation method, if `not self.is_healthy`:
    - Attempt a single recovery: `self._recover_session()`.
    - `_recover_session()` calls `self.engine.restart()`, re-imports baseline XML (`self.engine.call("import_build", xml=self.xml)`), re-queries base defenses/stats, and sets `self.is_healthy = True`.
    - If `_recover_session()` fails, the session remains `is_healthy = False` and the simulation call immediately returns `None`.
- **Rationale**: Isolates transient Lua or container crashes. Does not retry the bad item (which may have caused the crash via malformed syntax), but allows the next clean item to recover without requiring an application restart.

### 5. Baseline Restoration Error Logging
- **Decision**: In `companion/equipment/pob2_equipment_advisor.py`, replace all occurrences of `except Exception: pass` in simulation `finally` blocks with:
  ```python
  except Exception as exc:
      logging.getLogger(__name__).warning("Failed to restore baseline build in PoB2 session: %s", exc)
      self.is_healthy = False
      self.unhealthy_reason = f"Baseline restore failed: {exc}"
  ```
- **Rationale**: An un-restored engine means the baseline has been polluted by the candidate item. Silently continuing would poison all subsequent simulations. Marking the session unhealthy forces a clean baseline re-import on the next call.

### 6. Unified `merge_verdicts` Contract
- **Decision**: Create `merge_verdicts` in `companion.equipment.tactical_advisor`:
  ```python
  def merge_verdicts(
      policy_verdict: Verdict | str,
      tactical_verdict: Verdict | str | None,
  ) -> Verdict:
      pv = Verdict(policy_verdict) if isinstance(policy_verdict, str) else policy_verdict
      if tactical_verdict is None:
          return pv
      tv = Verdict(tactical_verdict) if isinstance(tactical_verdict, str) else tactical_verdict
      if tv == Verdict.REJECT:
          return Verdict.REJECT
      return pv
  ```
- Apply this identically across:
  - Weapon branch in `dashboard_api.py` (~line 478)
  - Ring branch in `dashboard_api.py` (~line 554)
  - Generic slot branch in `dashboard_api.py` (~line 604)
  - Standard engine fallback in `dashboard_api.py` (~line 777)
- **Rationale**: Eliminates divergent logic and ensures consistent veto-only semantics across all slots.

### 7. Engine Health Reporting in `/api/status`
- **Decision**: Update `get_dashboard_status()` and `dashboard_server.py` to extract engine health from the active or cached `Pob2EquipmentSession`:
  ```python
  "engine_status": {
      "available": getattr(sess, "is_available", False),
      "healthy": getattr(sess, "is_healthy", False),
      "unhealthy_reason": getattr(sess, "unhealthy_reason", None),
  }
  ```
  And inject `"engine_healthy": getattr(sess, "is_healthy", False)` into `status_data` for UI backward compatibility.

## Risks / Trade-offs

- **[Risk] Background reader thread blocking after process death**
  → *Mitigation*: The reader thread loop handles EOF (`""`) when `stdout` closes and catches `OSError`/`ValueError`. `PobEngine.close()` closes pipes and joins/terminates the thread with a short timeout.
- **[Risk] Stale candidate ID synchronization during recovery**
  → *Mitigation*: The engine lock is held during `_recover_session()`, and staleness checking (`is_stale(candidate_id)`) runs both before and after lock acquisition as already established in the codebase.
- **[Risk] Divergent test expectations on legacy tests**
  → *Mitigation*: Audit existing tests in `tests/unit/test_dashboard_api.py` and `tests/integration/equipment/`. Ensure all tests reflect veto-only merging, and add a dedicated 9x3 test matrix suite in `tests/unit/equipment/test_verdict_consolidation_matrix.py`.
