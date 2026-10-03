"""Deterministic analysis of declared dependencies and current source usage."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from backend.analysis.manifests import DependencyEvent, parse_manifest


PYTHON_FILES = {".py"}
JS_FILES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
SKIPPED_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
JS_IMPORT_RE = re.compile(
    r"(?:\bimport\s+(?:[^\"']+?\s+from\s+)?|\brequire\s*\(\s*)[\"']([^\"']+)[\"']"
)
PYTHON_IMPORT_ALIASES = {"beautifulsoup4": "bs4", "opencv-python": "cv2", "pillow": "PIL"}


@dataclass
class DependencyUsageEvidence:
    """A stable evidence record for one declared dependency."""

    dependency_name: str
    ecosystem: str
    manifest_file: str
    declared_version: Optional[str]
    current_usage_count: int = 0
    current_files: List[str] = field(default_factory=list)
    historical_dependency_events: List[DependencyEvent] = field(default_factory=list)
    current_usage_detected: bool = False
    confidence: str = "high"


def analyze_dependency_usage(
    repo_root: Path,
    historical_events: Sequence[DependencyEvent] = (),
) -> List[DependencyUsageEvidence]:
    """Analyze supported manifests and source files at the repository HEAD."""
    declarations = []
    for manifest_path in _manifest_paths(repo_root):
        try:
            content = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for entry in parse_manifest(manifest_path, content).values():
            if entry.kind in {"python", "js"}:
                declarations.append((manifest_path, entry))

    source_usage = _collect_source_usage(repo_root)
    evidence = []
    for manifest_path, entry in declarations:
        key = _dependency_key(entry.name, entry.kind)
        usage_count, files = source_usage.get(key, (0, []))
        matching_events = [
            event for event in historical_events
            if event.kind == entry.kind and _dependency_key(event.dep_name, event.kind) == key
        ]
        evidence.append(DependencyUsageEvidence(
            dependency_name=entry.name,
            ecosystem="python" if entry.kind == "python" else "javascript",
            manifest_file=manifest_path.relative_to(repo_root).as_posix(),
            declared_version=entry.version,
            current_usage_count=usage_count,
            current_files=files,
            historical_dependency_events=matching_events,
            current_usage_detected=usage_count > 0,
            confidence="high" if usage_count > 0 else "medium",
        ))
    return evidence


def _manifest_paths(repo_root: Path) -> Iterable[Path]:
    supported = {"requirements.txt", "requirements-dev.txt", "requirements.in", "pyproject.toml", "package.json"}
    for path in sorted(repo_root.rglob("*")):
        if path.is_file() and path.name.lower() in supported and not _is_skipped(path, repo_root):
            yield path


def _collect_source_usage(repo_root: Path) -> Dict[str, tuple[int, List[str]]]:
    counts: Dict[str, int] = {}
    files: Dict[str, List[str]] = {}
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or _is_skipped(path, repo_root):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if path.suffix in PYTHON_FILES:
            names = _python_imports(content)
        elif path.suffix in JS_FILES:
            names = _js_imports(content)
        else:
            names = []
        relative = path.relative_to(repo_root).as_posix()
        for name, ecosystem in names:
            key = _dependency_key(name, ecosystem)
            counts[key] = counts.get(key, 0) + 1
            files.setdefault(key, [])
            if relative not in files[key]:
                files[key].append(relative)
    return {key: (counts[key], files[key]) for key in counts}


def _python_imports(content: str) -> List[tuple[str, str]]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name.split(".")[0], "python") for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.module.split(".")[0], "python"))
    return imports


def _js_imports(content: str) -> List[tuple[str, str]]:
    return [(match.group(1), "js") for match in JS_IMPORT_RE.finditer(content)]


def _dependency_key(name: str, ecosystem: str) -> str:
    normalized = name.lower().replace("_", "-")
    if ecosystem == "python":
        normalized = PYTHON_IMPORT_ALIASES.get(normalized, normalized).lower()
    elif normalized.startswith("@"):
        normalized = "/".join(normalized.split("/")[:2])
    else:
        normalized = normalized.split("/")[0]
    return normalized


def _is_skipped(path: Path, repo_root: Path) -> bool:
    return bool(SKIPPED_DIRS.intersection(path.relative_to(repo_root).parts))