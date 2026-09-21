# Notification System Specification

## Purpose

Delivers low-friction gameplay notifications with alert deduplication, cooldowns, and safe-zone batching to prevent player distraction.

## Requirements

### Requirement: Alert Deduplication and Cooldown
The notification system SHALL deduplicate alerts sharing identical content or identity and SHALL enforce a configurable cooldown period to prevent repetitive alert spamming.

#### Scenario: Suppress duplicate alert within cooldown
- **WHEN** an alert with an active cooldown key is submitted within the cooldown window
- **THEN** the notification manager discards the duplicate alert without invoking delivery sinks

#### Scenario: Deliver alert after cooldown expiry
- **WHEN** an alert is submitted after the cooldown window for its key has elapsed
- **THEN** the notification manager accepts the alert and routes it according to policy

### Requirement: Safe-Zone Batching Policy
The notification system SHALL classify game areas into safe zones versus hostile combat zones, deferring non-critical advisories during combat and delivering critical alerts immediately.

#### Scenario: Critical alert breaks through in combat zone
- **WHEN** a critical severity alert is dispatched while the character is in a hostile combat zone
- **THEN** the notification manager delivers the alert immediately without queuing

#### Scenario: Non-critical advisory queued in combat zone
- **WHEN** a non-critical advisory alert is dispatched while the character is in a hostile combat zone
- **THEN** the notification manager enqueues the alert in the safe-zone buffer without delivering it to sinks

#### Scenario: Safe-zone entry flushes queued advisories
- **WHEN** a zone transition event to a recognized safe zone is received
- **THEN** the notification manager flushes all buffered safe-zone advisories to the delivery sinks

### Requirement: Pluggable Notification Sinks
The notification system SHALL support pluggable delivery sinks conforming to a standardized interface for in-memory recording, console logging, and desktop notifications.

#### Scenario: In-memory sink records sent notifications
- **WHEN** an accepted alert is delivered through the notification manager
- **THEN** configured delivery sinks receive the complete notification payload
