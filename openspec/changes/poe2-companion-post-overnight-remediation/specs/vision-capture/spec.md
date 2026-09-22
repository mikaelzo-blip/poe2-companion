# Spec Delta: Vision Capture

## Purpose

Provides a minimal, strictly read-only operating system screen and bounded region capture adapter for Windows, establishing a strict architectural boundary between screen pixel capture and downstream visual extraction, while acquiring display pixels without input automation, memory injection, or unconsented persistence.

## ADDED Requirements

### Requirement: Architectural Separation of Capture and Visual Extraction
The system SHALL strictly decouple screen capture from visual extraction as two distinct architectural layers:
1. SCREEN CAPTURE (`OS pixels -> CapturedFrame`): Acquires raw display pixel buffers into an immutable structured frame.
2. VISUAL EXTRACTION (`CapturedFrame -> structured observation`): Converts frame pixels into structured game domain observations (such as character panel stats or tooltip observations).

The existing text and regex parsers in `companion/vision/parser.py` SHALL NOT be treated as raw-pixel extractors. In the absence of an integrated optical character recognition (OCR) or computer vision extraction model in this remediation, successful screen capture SHALL only establish `CapturedFrame` availability. Game state models, including `CharacterPanelStats`, SHALL evaluate to `UNKNOWN` until a supported visual extractor supplies evidence from the frame. Text fixtures and manually provided extracted text SHALL remain separate, decoupled test and input paths. The M7 subsystem SHALL be classified and described as capture-capable, and SHALL NOT claim automatic visual interpretation of raw captured pixels.

#### Scenario: Successful screen capture does not infer domain observations without an extractor
- **WHEN** a screen or bounded region capture succeeds and produces a valid `CapturedFrame`
- **THEN** `CapturedFrame` availability is established, but downstream `CharacterPanelStats` evaluates to `UNKNOWN` until a verified visual extractor processes the frame

#### Scenario: Text fixtures remain distinct from raw pixel capture
- **WHEN** downstream parser unit tests or manual inputs are evaluated
- **THEN** text fixtures are consumed directly via the decoupled text parsing interface without invoking or simulating the screen capture pipeline

### Requirement: CapturedFrame Pixel Data Contract
The system SHALL represent all captured display frames via an immutable `CapturedFrame` contract containing explicit pixel format and dimensional metadata:
- `format`: Pixel format and byte order (`PixelFormat.BGRA` or `PixelFormat.RGBA`, 8 bits per channel, unsigned byte)
- `width`: Positive integer frame width in pixels
- `height`: Positive integer frame height in pixels
- `channels`: Integer channel count (4 for BGRA/RGBA)
- `row_stride`: Integer row stride representing bytes per horizontal scanline (`width * channels` or 4-byte aligned bitmap stride)
- `region`: `CaptureRegion` specifying bounding coordinates (`left`, `top`, `width`, `height`) or `None` if full monitor
- `source_id`: Display monitor or adapter identifier (e.g. monitor index or display handle)
- `captured_at`: ISO 8601 UTC timestamp of frame acquisition
- `backend`: Provenance identifier of the capture backend (`mss` or `fake`)

The system SHALL enforce that raw pixel byte buffers cannot be silently cast, coerced, or treated as text strings.

#### Scenario: CapturedFrame validates complete pixel contract
- **WHEN** a screen capture is produced by a capture backend
- **THEN** the returned `CapturedFrame` exposes valid `format`, `width`, `height`, `channels`, `row_stride`, `region`, `source_id`, `captured_at`, and `backend` metadata matching the captured buffer size

#### Scenario: Rejection of raw pixel buffers as text input
- **WHEN** raw pixel byte buffers or a `CapturedFrame` instance are passed directly to text parsing functions
- **THEN** the system rejects the input with a type error and SHALL NOT attempt regex matching or silent string decoding on raw binary pixels

### Requirement: Read-Only Screen and Bounded Region Capture
The system SHALL capture display pixels from the designated screen or a bounded sub-region as an uncompressed raw pixel frame. The capture adapter SHALL only perform read-only capture operations and SHALL NOT include or invoke any input simulation, keyboard events, mouse movement, window manipulation, or OS hooks.

#### Scenario: Successful full screen capture
- **WHEN** a full screen capture is requested on an active display session
- **THEN** the adapter returns a `CapturedFrame` adhering to the pixel contract with dimensions matching the active monitor

#### Scenario: Bounded sub-region capture
- **WHEN** a sub-region defined by bounding coordinates (`left`, `top`, `width`, `height`) within the display boundaries is requested
- **THEN** the adapter returns a `CapturedFrame` matching the exact requested dimensions cropped from the screen coordinates

### Requirement: Isolated Capture Failure and Uncertainty
The system SHALL return structured unavailable or unknown evidence upon any capture failure (including locked desktop, missing display context, or OS permission denial) and SHALL NOT fabricate visual observations or fall back to synthetic placeholder values.

#### Scenario: Capture failure when desktop is unavailable
- **WHEN** the OS desktop cannot be captured due to session lock or permission denial
- **THEN** the capture operation produces a structured failure result with verification state `UNKNOWN` and error classification

### Requirement: Non-Persistent In-Memory Frame Processing
The system SHALL keep captured screen frames in volatile memory during classification and extraction, and SHALL NOT write raw captured screenshots to persistent disk storage unless explicit caching is configured under approved time-to-live and privacy policies.

#### Scenario: Ephemeral extraction without disk persistence
- **WHEN** a screen capture is processed for character panel stats or tooltip classification under default configuration
- **THEN** no screenshot image file is written to disk

### Requirement: Strict Input and Process Isolation Compliance
The capture adapter module SHALL remain completely isolated from any user input APIs, game process memory inspection, window injection, or accessibility automation libraries.

#### Scenario: Automated compliance scan for prohibited imports
- **WHEN** the codebase is scanned by the no-input compliance suite
- **THEN** the vision capture adapter imports zero modules associated with input simulation, keyboard or mouse control, process memory reading, or dynamic library injection
