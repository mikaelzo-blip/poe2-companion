# Companion CLI Specification

## Purpose

Provides a lightweight, deterministic command-line interface v0.1 for evaluating character state, listing generated player objectives, displaying the next actionable objective, and writing structured runtime artifacts without background daemons or network dependencies.

## Requirements

### Requirement: Objectives Inspection Subcommands
The CLI SHALL provide an `objectives` command group supporting `list` and `next` actions:
- `companion objectives list`: Evaluates the active (or specified `--id`) character state and outputs all active objectives in deterministic priority order.
- `companion objectives next`: Evaluates the character state and outputs only the highest-priority actionable objective.
- Both subcommands SHALL support an optional `--json` flag to emit raw structured JSON instead of human-readable text.
- Both subcommands SHALL support an optional `--runtime <dir>` argument defaulting to `runtime`.

#### Scenario: List objectives in human-readable format
- **WHEN** user executes `companion objectives list`
- **THEN** all current objectives are printed in deterministic order with categorical priority, action instructions, and source references

#### Scenario: Output next objective as JSON
- **WHEN** user executes `companion objectives next --json`
- **THEN** only the single top-priority objective is output formatted as valid JSON

#### Scenario: No actionable objectives handled cleanly
- **WHEN** character state has no pending objectives and user executes `companion objectives next`
- **THEN** the CLI outputs `NO_ACTIONABLE_OBJECTIVE` with informative status indicating alignment

### Requirement: Character Evaluation Subcommand and CURRENT_OBJECTIVE Artifact
The CLI SHALL provide an `evaluate` command:
- `companion evaluate <character_state_path>`: Evaluates the given character state file against target build rules and transition state.
- Emits the current highest-priority objective to stdout (formatted or JSON with `--json`).
- Atomically writes the evaluated current objective and metadata to a structured JSON artifact named `CURRENT_OBJECTIVE.json` in the runtime directory (or specified `--out` path).

#### Scenario: Evaluate command writes CURRENT_OBJECTIVE.json
- **WHEN** user executes `companion evaluate path/to/character.json`
- **THEN** the CLI derives objectives, displays the top objective, and writes `CURRENT_OBJECTIVE.json` to disk

#### Scenario: Missing character file raises clear error
- **WHEN** user executes `companion evaluate non_existent_file.json`
- **THEN** the CLI exits with non-zero status code and prints a descriptive file-not-found error message to stderr

### Requirement: Deterministic Structured Template Output
The CLI SHALL format human-readable objectives using a deterministic, four-part block template:
- Header: `[<PRIORITY_RANK>] <Objective Title>`
- Action: `DO NOW: <Specific concrete action to take>`
- Rationale: `WHY: <Underlying factual cause and progression impact>`
- Source: `SOURCE: <Source provenance, e.g. rule identifier or target build snapshot>`

The formatting SHALL be entirely deterministic and SHALL NOT invoke external language models or generate variable conversational text.

#### Scenario: Structured template rendering
- **WHEN** an objective candidate is rendered in human-readable mode
- **THEN** the output contains the exact tags `[<PRIORITY>]`, `DO NOW:`, `WHY:`, and `SOURCE:`

### Requirement: Batch Offline Execution and Zero-Daemon Invariant
The CLI SHALL execute purely in synchronous batch mode. The CLI SHALL NOT start persistent background processes, spawn daemon services, open network sockets, or perform live game injection or input synthesis. The implementation SHALL maintain full compliance with the static no-input guard.

#### Scenario: CLI execution completes synchronously without background daemons
- **WHEN** any CLI subcommand is invoked
- **THEN** the process performs evaluation, emits output, and exits cleanly without leaving background threads or subprocesses running
