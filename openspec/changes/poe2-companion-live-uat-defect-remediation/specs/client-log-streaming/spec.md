# Spec Delta: Client Log Streaming

## Purpose

Provides reliable, non-dropping client log streaming and event parsing that guarantees backlog continuity across batch polls, robust binary line decoding, and accurate PoE2 level-up format parsing.

## ADDED Requirements

### Requirement: Bounded Incremental Stream Byte Offset Tracking
The system SHALL advance the persistent client log read offset strictly in bytes and strictly through the boundary of the last complete newline-terminated record (`b"\n"`) actually consumed during a poll operation. When a batch size limit (max_lines) is reached, any unconsumed bytes or lines beyond that limit SHALL NOT advance the read offset and SHALL remain available for immediate sequential processing on subsequent poll operations. Incomplete trailing lines SHALL remain unread until completed.

#### Scenario: Backlog exceeding poll batch limit retains unread lines with byte-exact offset
- **WHEN** the client log contains 2,500 new complete unread lines and a poll operation is executed with max_lines set to 1,000
- **THEN** the poll operation SHALL consume exactly 1,000 lines, advance the byte read offset exactly through line 1,000, and leave the remaining 1,500 lines unconsumed

#### Scenario: Subsequent poll continues seamlessly from next byte position
- **WHEN** a second poll operation is executed following a batch-limited poll
- **THEN** the tailer SHALL continue reading from the exact byte position following line 1,000 without skipping any lines and without reprocessing previously consumed lines

#### Scenario: Incomplete trailing byte line held until completed
- **WHEN** the final line in a read buffer does not terminate with a newline character (`b"\n"`)
- **THEN** the read offset SHALL not advance past the start of the incomplete line, and the line SHALL be read and processed in full once completed by subsequent file writes

#### Scenario: Log file truncation or rotation resets byte offset
- **WHEN** the client log file size becomes strictly less than the current byte read offset
- **THEN** the tailer SHALL reset its byte read offset to zero without raising an exception

### Requirement: Robust Binary Line Decoding
The system SHALL decode complete byte records using UTF-8 with character replacement (`errors="replace"`). Malformed byte sequences, invalid encodings, or non-ASCII characters SHALL NOT crash the tailer, SHALL NOT corrupt byte offset progression, and SHALL NOT prevent subsequent valid log events from being extracted.

#### Scenario: Non-ASCII and malformed bytes decoded safely
- **WHEN** a complete log line contains non-ASCII characters or invalid byte sequences
- **THEN** the line SHALL be decoded using replacement characters without throwing an exception and the byte offset SHALL advance normally past the line

#### Scenario: Malformed line safely ignored while subsequent valid line is parsed
- **WHEN** a malformed or undecodable log line is immediately followed by a valid level-up log line
- **THEN** the malformed line SHALL evaluate to None without emitting an event and the subsequent level-up event SHALL be extracted successfully

### Requirement: PoE2 Level-Up Event Parsing with Class Tokens
The system SHALL parse Path of Exile 2 level-up announcement log lines formatted with character names and optional parenthetical class tokens, while preserving parsing support for level-up lines without class tokens.

#### Scenario: PoE2 level-up with parenthetical class token parsed
- **WHEN** a log line containing `: BOMSHAK (Mercenary) is now level 11` is processed
- **THEN** the parser SHALL return a level-up event with character_name `BOMSHAK`, level `11`, and optional class token `Mercenary`

#### Scenario: Legacy level-up without class token parsed
- **WHEN** a log line containing `: Mercenary_Exile is now level 52` is processed
- **THEN** the parser SHALL return a level-up event with character_name `Mercenary_Exile` and level `52`

#### Scenario: Unrelated system and chat lines ignored
- **WHEN** a log line containing player whispers, chat prefixes (`@From`, `@To`, `$`, `#`, `%`), or unrecognized system text is processed
- **THEN** the parser SHALL return None without emitting any event
