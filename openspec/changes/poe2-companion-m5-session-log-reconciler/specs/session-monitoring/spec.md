# Spec Delta

## Purpose

Detects Path of Exile 2 process execution state and tails local client log files in read-only mode with rotation safety and strict privacy filtering.

## ADDED Requirements

### Requirement: Process Presence Detection
The system SHALL monitor local operating system process execution to detect whether Path of Exile 2 (`PathOfExileSteam.exe` or `PathOfExile.exe`) is active, transitioning between `IDLE`, `RUNNING`, and `TERMINATED` states without acquiring elevated permissions or attaching debuggers.

#### Scenario: Game process launches
- **WHEN** the user starts Path of Exile 2 and process polling detects an active game executable
- **THEN** the monitor SHALL emit a process event indicating the `RUNNING` state with executable name and process ID

#### Scenario: Game process terminates
- **WHEN** an active game executable process exits or is terminated
- **THEN** the monitor SHALL emit a process event indicating the `TERMINATED` state and return to `IDLE` polling

### Requirement: Read-Only Client.txt Tailer
The system SHALL tail the local game log file (`Client.txt`) strictly in read-only mode, maintaining stream position, safely handling line chunking, incomplete trailing lines, and detecting file rotation or truncation.

#### Scenario: Incremental log line streaming
- **WHEN** new lines are appended to `Client.txt`
- **THEN** the tailer SHALL read newly added bytes without seeking back or modifying the file, buffering incomplete trailing segments until the newline character is received

#### Scenario: Log file truncation or rotation
- **WHEN** `Client.txt` file size shrinks below current offset or file inode/creation identity changes
- **THEN** the tailer SHALL reset its read offset to zero and continue streaming from the beginning of the new file without crashing or losing subsequent lines

### Requirement: Privacy Filter Invariant
The system SHALL parse only recognized system patterns (zone entries, level-up announcements, and death notifications) and SHALL immediately discard player whisper messages, guild chat, global chat, and party chat.

#### Scenario: Whisper and chat messages dropped
- **WHEN** a log line matching chat patterns (starting with `@From`, `@To`, `$`, `#`, or `%`) is encountered
- **THEN** the filter SHALL immediately discard the line without emitting an observation event or writing to disk

#### Scenario: Recognized game events parsed
- **WHEN** a log line matches an area entry (`Generating level ... area "..."` or `Entered area "..."`), level-up (`... is now level ...`), or death notification (`... has been slain`)
- **THEN** the filter SHALL normalize the line into a typed observation event containing extracted semantic payload and timestamp
