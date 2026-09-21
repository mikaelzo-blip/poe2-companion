# Spec Delta

## Purpose

Generates structured, deterministic post-session recaps from normalized journey history without hallucinating unobserved events.

## ADDED Requirements

### Requirement: Post-Session Milestone Summarization
The session recap engine SHALL aggregate journey history entries to produce a structured summary of game progression, levels gained, zones visited, and player deaths.

#### Scenario: Generate recap from journey events
- **WHEN** a session recap is requested with valid journey history records
- **THEN** the recap engine computes accurate totals for zones visited, level changes, and deaths

#### Scenario: Handle empty session gracefully
- **WHEN** a session recap is requested with no recorded journey events
- **THEN** the recap engine emits a valid zero-count summary without raising an error

### Requirement: Structured Recap Formatting
The session recap engine SHALL format session summaries into deterministic human-readable text and machine-readable JSON formats.

#### Scenario: Emit JSON recap artifact
- **WHEN** JSON recap output is requested
- **THEN** the recap engine serializes the complete metrics and milestones structure
