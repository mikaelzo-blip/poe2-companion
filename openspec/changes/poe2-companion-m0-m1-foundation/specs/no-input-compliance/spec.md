# Spec Delta

## Purpose

Enforces the read-only, non-interactive boundary of the companion as a defense-in-depth compliance check that enforces the project's prohibited input/control dependencies and known API patterns at static-analysis time.

## ADDED Requirements

### Requirement: Static Defense-in-Depth Compliance Check for Prohibited Input and Control APIs
The system SHALL inspect Python source files within the scope `companion/**/*.py` using static abstract syntax tree (AST) analysis and SHALL fail verification if any prohibited input-simulation, keyboard/mouse hooking, or memory-injection libraries or known API patterns are imported or invoked. The compliance scanner is a lightweight defense-in-depth check rather than an absolute mathematical proof of impossibility. The scanner SHALL explicitly exclude non-production and generated directories (such as virtual environments `.venv/`, test fixture files, `docs/`, `data/`, `runtime/`, and OpenSpec artifacts).

#### Scenario: Clean companion modules pass compliance check
- **WHEN** the static no-input guard analyzes companion modules under `companion/` that adhere to read-only architecture
- **THEN** the compliance check passes with zero violations reported

#### Scenario: Direct prohibited module import detected and rejected
- **WHEN** any module under `companion/**/*.py` contains a direct import of a prohibited package (such as `import pyautogui` or `import pynput`)
- **THEN** the scanner fails and reports the offending file path, line number, and imported module name

#### Scenario: From-import of prohibited module or symbol detected and rejected
- **WHEN** any module under `companion/**/*.py` contains a `from ... import ...` statement referencing a prohibited module or symbol (such as `from pynput import mouse` or `from ctypes.windll.user32 import SendInput`)
- **THEN** the scanner fails and reports the offending file path, line number, and imported symbol

#### Scenario: Aliased prohibited import detected and rejected
- **WHEN** a prohibited library or function is imported with an alias (such as `import pyautogui as pag` or `from pynput.keyboard import Controller as KCtrl`)
- **THEN** the scanner detects the underlying prohibited module or symbol, fails verification, and reports the file and alias mapping

#### Scenario: Known prohibited attribute lookup or call token detected and rejected
- **WHEN** any module under `companion/**/*.py` references known prohibited native input call tokens (such as `SendInput`, `keybd_event`, or `mouse_event`)
- **THEN** the scanner fails and reports the offending file path, line number, and prohibited symbol reference

#### Scenario: Excluded directories are not scanned for violations
- **WHEN** compliance scanning is executed
- **THEN** test fixture files, virtual environments, documentation, runtime data, and OpenSpec artifacts containing documentation or synthetic test references are excluded from the scan
