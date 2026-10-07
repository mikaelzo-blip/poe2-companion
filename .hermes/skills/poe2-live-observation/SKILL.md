---
name: poe2-live-observation
description: "Start or resume live development observation review for active PoE2 companion session."
version: 1.0.0
author: PoE2 Companion
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [poe2, observation, live-review, bridge]
---

# PoE2 Live Development Observation Skill

Review runtime observations, user markers, and telemetry from an active Path of Exile 2 companion session.

## Strict Write Allowlist (MANDATORY)

While live observation is active, Hermes operates under a strict sandbox write allowlist.
You are permitted to write ONLY these files in the active session's `live_analysis/` directory:
1. `runtime/observations/<session>/live_analysis/review_claims/<review_batch_id>.<claim_id>.json` (immutable claim artifact)
2. `runtime/observations/<session>/live_analysis/review_claim_status/<review_batch_id>.<claim_id>.json` (self-owned lease renewal)
3. `runtime/observations/<session>/live_analysis/review_responses/<review_batch_id>.<claim_id>.json` (claim-specific response candidate)
4. `runtime/observations/<session>/live_analysis/hermes_review_status.json` (heartbeat and review liveness)

### Strictly Forbidden Writes
You must NEVER write, modify, or delete:
- Companion source code (`companion/**`)
- Tests (`tests/**`)
- OpenSpec artifacts (`openspec/**`)
- Objective rules or build data (`rules/**`, `data/**`)
- CharacterState or loadouts (`runtime/characters/**`)
- Raw evidence files (`runtime/observations/<session>/*.jsonl`)
- Reader cursor state (`reader_state.json`)
- Review cursor (`hermes_review_cursor.json`)

## Approved Read Scope
- `runtime/observations/<session>/live_analysis/review_requests/*.json`
- `runtime/observations/<session>/session_manifest.json`
- Local evidence streams at specified byte offsets
- Bounded `Client.txt` byte ranges around known event offsets

## Workflow Procedure

1. **Discover Active Session**:
   Find the newest open session in `runtime/observations/` by checking `session_manifest.json` (`status: "OPEN"`).

2. **Discover Pending Requests**:
   Scan `runtime/observations/<session>/live_analysis/review_requests/*.json`.
   Prioritize requests with user markers (`priority == "HIGH_MARKER"`) or runtime errors (`priority == "HIGH_ERROR"`) before routine batches.

3. **Inspect Existing Findings**:
   Read `existing_findings` in the request envelope. If observed anomalies corroborate an existing issue, use `UPDATE_FINDING` with the matching `target_finding_id`.

4. **Acquire Claim**:
   Write `review_claims/<review_batch_id>.<claim_id>.json` using atomic write (.tmp -> rename) with `lease_expires_at = now + 180s`.

5. **Read Evidence & Reason**:
   Read evidence items referenced in `evidence_ids`. Analyze objectively without hallucinations.

6. **Formulate Finding Operations**:
   - `CREATE_FINDING`: For novel anomalies or defects. Specify `category`, `semantic_issue_key`, `classification`, `safe_summary`, and supporting `evidence_refs`.
   - `UPDATE_FINDING`: For corroborating existing findings. Must provide exact `target_finding_id`.
   - `NO_FINDING`: When the observed sequence is clean and nominal.

7. **Ensure 100% Evidence Accounting**:
   `accounted_evidence_ids` in `ReviewResponseEnvelope` MUST exactly match `set(request.evidence_ids)`.

8. **Atomically Write Candidate Response**:
   Write `review_responses/<review_batch_id>.<claim_id>.json` via `.tmp` file and atomic rename.

9. **Update Review Heartbeat**:
   Update `hermes_review_status.json` with active timestamp and current reviewed sequence.
