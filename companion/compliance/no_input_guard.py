"""Static defense-in-depth compliance scanner for PoE2 companion codebase.

Enforces that unattended companion modules do not import or invoke game-control,
input-simulation, or hooking mechanisms at static-analysis time.

Note: This is a defense-in-depth static AST check designed to catch accidental or
intentional introduction of input automation libraries during development and CI.
It is not an absolute mathematical guarantee against runtime reflection or obfuscation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# Prohibited top-level or dotted module names
PROHIBITED_MODULES: frozenset[str] = frozenset({
    "pyautogui",
    "pynput",
    "keyboard",
    "mouse",
    "cua_driver",
})

# Prohibited function/method/attribute call or access tokens
PROHIBITED_TOKENS: frozenset[str] = frozenset({
    "SendInput",
    "keybd_event",
    "mouse_event",
})

# Default directory exclusion patterns
EXCLUDED_PARTS: frozenset[str] = frozenset({
    ".venv",
    "venv",
    "env",
    ".pytest_cache",
    "__pycache__",
    "docs",
    "data",
    "runtime",
    "openspec",
    ".hermes",
    "tests",
})


@dataclass(frozen=True)
class ComplianceViolation:
    """Represents a single static compliance violation."""
    file_path: str
    line: int
    symbol: str
    category: str
    details: str

    def __str__(self) -> str:
        return f"[{self.category}] {self.file_path}:{self.line} -> prohibited symbol '{self.symbol}': {self.details}"


class ComplianceViolationError(Exception):
    """Raised when one or more compliance violations are detected."""
    def __init__(self, violations: Sequence[ComplianceViolation]) -> None:
        self.violations = list(violations)
        summary = "\n".join(str(v) for v in self.violations)
        super().__init__(f"Detected {len(self.violations)} no-input compliance violation(s):\n{summary}")


class _ComplianceASTVisitor(ast.NodeVisitor):
    """AST visitor detecting prohibited imports and call tokens."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.violations: list[ComplianceViolation] = []

    def _check_module_name(self, name: str, line: int) -> None:
        base_mod = name.split(".")[0]
        if base_mod in PROHIBITED_MODULES or name in PROHIBITED_MODULES:
            self.violations.append(
                ComplianceViolation(
                    file_path=self.file_path,
                    line=line,
                    symbol=name,
                    category="PROHIBITED_IMPORT",
                    details=f"Direct import of prohibited module '{name}'",
                )
            )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module_name(alias.name, node.lineno)
            if alias.asname and (alias.name.split(".")[0] in PROHIBITED_MODULES or alias.name in PROHIBITED_MODULES):
                self.violations.append(
                    ComplianceViolation(
                        file_path=self.file_path,
                        line=node.lineno,
                        symbol=alias.asname,
                        category="PROHIBITED_ALIAS_IMPORT",
                        details=f"Aliased import '{alias.name}' as '{alias.asname}'",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        base_mod = mod.split(".")[0]
        if base_mod in PROHIBITED_MODULES or mod in PROHIBITED_MODULES:
            self.violations.append(
                ComplianceViolation(
                    file_path=self.file_path,
                    line=node.lineno,
                    symbol=mod,
                    category="PROHIBITED_FROM_IMPORT",
                    details=f"Import from prohibited module '{mod}'",
                )
            )
        for alias in node.names:
            if alias.name in PROHIBITED_TOKENS:
                self.violations.append(
                    ComplianceViolation(
                        file_path=self.file_path,
                        line=node.lineno,
                        symbol=alias.name,
                        category="PROHIBITED_SYMBOL_IMPORT",
                        details=f"Import of prohibited symbol '{alias.name}' from '{mod}'",
                    )
                )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in PROHIBITED_TOKENS:
            self.violations.append(
                ComplianceViolation(
                    file_path=self.file_path,
                    line=node.lineno,
                    symbol=node.id,
                    category="PROHIBITED_TOKEN_USAGE",
                    details=f"Direct reference to prohibited token '{node.id}'",
                )
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in PROHIBITED_TOKENS:
            self.violations.append(
                ComplianceViolation(
                    file_path=self.file_path,
                    line=node.lineno,
                    symbol=node.attr,
                    category="PROHIBITED_ATTRIBUTE_USAGE",
                    details=f"Access of prohibited attribute '{node.attr}'",
                )
            )
        self.generic_visit(node)


def scan_file(file_path: str | Path) -> list[ComplianceViolation]:
    """Scan a single Python source file for compliance violations."""
    path = Path(file_path)
    if not path.is_file() or path.suffix != ".py":
        return []

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [
            ComplianceViolation(
                file_path=str(path),
                line=getattr(e, "lineno", 1) or 1,
                symbol="PARSE_ERROR",
                category="SCAN_ERROR",
                details=f"Failed to parse source: {e}",
            )
        ]

    visitor = _ComplianceASTVisitor(str(path))
    visitor.visit(tree)
    # Deduplicate any duplicate reports on the same line/symbol
    seen: set[tuple[str, int, str]] = set()
    unique_violations: list[ComplianceViolation] = []
    for v in visitor.violations:
        key = (v.file_path, v.line, v.symbol)
        if key not in seen:
            seen.add(key)
            unique_violations.append(v)
    return unique_violations


def should_exclude(path: Path) -> bool:
    """Check if the given path should be excluded from compliance checks."""
    parts = set(path.parts)
    return any(excluded in parts for excluded in EXCLUDED_PARTS)


def scan_directory(
    root_dir: str | Path,
    file_pattern: str = "**/*.py",
    exclude_parts: Sequence[str] | None = None,
) -> list[ComplianceViolation]:
    """Scan directory recursively for Python files, respecting exclusions."""
    root = Path(root_dir)
    exclusions = set(exclude_parts) if exclude_parts is not None else EXCLUDED_PARTS

    violations: list[ComplianceViolation] = []
    for py_file in root.glob(file_pattern):
        parts = set(py_file.parts)
        if any(exc in parts for exc in exclusions):
            continue
        violations.extend(scan_file(py_file))
    return violations


def assert_no_input_compliance(
    companion_root: str | Path | None = None,
) -> None:
    """Assert that the companion codebase satisfies no-input compliance."""
    if companion_root is None:
        companion_root = Path(__file__).resolve().parent.parent  # companion/

    root = Path(companion_root)
    violations = scan_directory(root)
    if violations:
        raise ComplianceViolationError(violations)
