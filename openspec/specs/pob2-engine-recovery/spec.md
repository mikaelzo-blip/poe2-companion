# pob2-engine-recovery Specification

## Purpose
Enforces predictable IPC timeout limits and automated process recovery for the headless PoB2 calculation engine, while surfacing runtime health status to client consumers.

## Requirements

### Requirement: Engine call timeout enforcement
The PoB2 engine SHALL enforce a strict timeout (`call_timeout`) on every IPC command sent to the Lua subprocess without using platform-specific pipe polling like `select`. If the engine subprocess does not return a newline-terminated response within the configured timeout duration, the system MUST terminate the subprocess, release internal synchronization locks, and raise `EngineTimeoutError` (subclassing `EngineError`).

#### Scenario: Lua engine hangs during complex calculation
- **WHEN** an IPC call is dispatched to the engine and the Lua process takes longer than `call_timeout` seconds to produce a response
- **THEN** the system terminates the subprocess, cleans up transport resources, releases the engine lock, and raises `EngineTimeoutError` without deadlocking subsequent calls

#### Scenario: Timed-out command releases internal mutex
- **WHEN** an IPC call times out and raises `EngineTimeoutError`
- **THEN** the engine lock is not left locked, allowing subsequent recovery or lifecycle calls to acquire the lock

### Requirement: Engine restart and readiness recovery
The PoB2 engine SHALL provide `restart()` and `ensure_alive()` mechanisms that restart a dead or terminated subprocess, wait up to `ready_timeout` for the `MCP_ENTRY_READY` sentinel on stderr, and re-establish line-buffered communication channels while preserving internal lock semantics.

#### Scenario: Restarting terminated engine
- **WHEN** `restart()` is invoked on an engine whose subprocess was terminated or killed
- **THEN** the system closes prior pipes, launches a fresh subprocess, drains stderr in a daemon thread, waits for the readiness sentinel, and transitions to a ready state

#### Scenario: Ensure alive on already running engine
- **WHEN** `ensure_alive()` is called on an engine that is already running and responsive
- **THEN** the system verifies the process is active without restarting or terminating the existing healthy process

### Requirement: Session health tracking and degraded state
The equipment session (`Pob2EquipmentSession`) SHALL maintain an explicit health state (`is_healthy: bool` and `unhealthy_reason: str | None`). If any simulation or IPC command raises an `EngineError` (including `EngineTimeoutError`), the session MUST immediately mark itself as unhealthy (`is_healthy = False`), record the error details, and return an empty or unavailable evaluation result without raising unhandled exceptions to callers.

#### Scenario: Engine crash marks session unhealthy
- **WHEN** an IPC command fails due to a crashed engine process or broken pipe
- **THEN** `Pob2EquipmentSession.is_healthy` becomes `False`, `unhealthy_reason` records the failure, and the calling method returns `None`

#### Scenario: Simulation failure is not automatically retried in-flight
- **WHEN** a candidate simulation fails with an engine error
- **THEN** the session marks itself unhealthy and discards the failed candidate immediately without executing an automatic in-flight retry of that same calculation

### Requirement: Single-restart recovery on subsequent session call
When a session is marked unhealthy, the subsequent simulation request SHALL attempt a single recovery sequence: restart the engine once, re-import the baseline character XML (`import_build`), and re-establish baseline defenses before attempting the new candidate simulation. If recovery fails, the session MUST remain unhealthy.

#### Scenario: Subsequent request succeeds after restarting dead engine
- **WHEN** a new candidate is submitted to an unhealthy session whose baseline XML is known
- **THEN** the session restarts the engine, imports the baseline XML, restores health status (`is_healthy = True`), and proceeds with simulating the new candidate

#### Scenario: Recovery failure maintains unhealthy state
- **WHEN** recovery is attempted on an unhealthy session but the restart or baseline re-import fails
- **THEN** the session remains unhealthy (`is_healthy = False`), updates `unhealthy_reason`, and aborts the simulation returning `None`

### Requirement: Baseline restoration failure detection and logging
The equipment session SHALL wrap all simulation baseline restoration operations in guarded error handlers that log warnings on failure rather than silently swallowing exceptions with `pass`. If baseline restoration fails in a `finally` block, the session MUST mark itself unhealthy to prevent baseline pollution on future simulations.

#### Scenario: Baseline restoration fails after simulation
- **WHEN** the `import_build` restoration call in a simulation `finally` block raises an exception
- **THEN** the session logs a warning message with the failure details, sets `is_healthy = False`, and sets `unhealthy_reason` to describe the restoration failure

### Requirement: Engine health reporting in API status
The `/api/status` endpoint and `get_dashboard_status()` SHALL expose the operational health of the PoB2 calculation engine, including whether an engine session is active, whether it is healthy, and the latest error or degradation reason if unhealthy.

#### Scenario: Status query with healthy engine
- **WHEN** a client performs a `GET /api/status` request while the engine is running and healthy
- **THEN** the response includes `engine_status` with `available: true`, `healthy: true`, and `error: null`

#### Scenario: Status query with unhealthy engine
- **WHEN** a client performs a `GET /api/status` request after an engine timeout or crash
- **THEN** the response reflects `healthy: false` and includes the explanatory failure message
