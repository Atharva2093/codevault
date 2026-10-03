"""Dependency manifest parsing + diff extraction.

Strategy:
- requirements.txt / .in: line-by-line diff (+/- lines map 1:1 to deps)
- pyproject.toml / poetry.lock: parse with tomllib (stdlib >= 3.11), compare dicts
- package.json: parse with json, compare deps/peer/optional/dev dependencies
- package-lock.json / pnpm-lock.yaml / yarn.lock: best-effort unified diff line extraction

All parsing is tolerant: bad lines are skipped, not raised.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

try:
    import tomllib  # stdlib 3.11+
except ImportError:
    import tomli as tomllib  # fallback; not expected in 3.14


# ---- public API ----

@dataclass
class DepEntry:
    """A single dependency entry from a manifest."""
    name: str
    version: Optional[str] = None
    raw_line: Optional[str] = None  # original line text (for evidence)
    kind: str = "python"            # "python" | "js" | "lock" | "other"


@dataclass
class DependencyEvent:
    """A diff event: added / removed / changed."""
    dep_name: str
    kind: str
    manifest_file: str
    action: str           # "added" | "removed" | "changed"
    version: Optional[str] = None
    line_number: Optional[int] = None
    raw_line: Optional[str] = None
    diff_line: Optional[str] = None
    old_version: Optional[str] = None
    new_version: Optional[str] = None


ManifestDict = Dict[str, DepEntry]  # dep_name -> DepEntry


def parse_manifest(path: Path, content: str) -> ManifestDict:
    """Parse a manifest file's content into a dict of dep_name -> DepEntry."""
    name = path.name.lower()
    if name in ("requirements.txt", "requirements-dev.txt", "requirements.in"):
        return _parse_requirements(path, content)
    if name == "pyproject.toml":
        return _parse_pyproject(path, content)
    if name == "poetry.lock":
        return _parse_poetry_lock(path, content)
    if name == "package.json":
        return _parse_package_json(path, content)
    if name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
        return _parse_lock_file(path, content)
    return {}


def diff_manifests(
    manifest_path: str,
    parent_content: Optional[str],
    head_content: Optional[str],
) -> List[DependencyEvent]:
    """Compare two manifest snapshots, return dependency events.

    For requirements.txt and lock files we use a line-based unified diff.
    For structured formats we diff the parsed dicts.
    """
    name = Path(manifest_path).name.lower()

    if name in ("requirements.txt", "requirements-dev.txt", "requirements.in"):
        return _diff_requirements(manifest_path, parent_content or "", head_content or "")
    if name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
        # Lock files are large and line-oriented; line diff is more robust than JSON parse
        return _diff_lock_file(manifest_path, parent_content or "", head_content or "")
    # Structured compare
    old = parse_manifest(Path(manifest_path), parent_content) if parent_content else {}
    new = parse_manifest(Path(manifest_path), head_content) if head_content else {}
    return _diff_dicts(manifest_path, old, new)


# ---- requirements.txt parsing ----

REQ_LINE_RE = re.compile(
    r"^\s*(?:-e\s+)?(?:git\+|https?://)?([^#\s;]+?)(?:\[[^\]]+\])?\s*(?:[=<>~!]=?\s*([^\s#;]+))?\s*(?:[;#].*)?$"
)


def _parse_requirements(path: Path, content: str) -> ManifestDict:
    deps: ManifestDict = {}
    for i, line in enumerate(content.splitlines(), start=1):
        m = REQ_LINE_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        version = m.group(2).strip() if m.group(2) else None
        # Normalize git/URL deps: use the last path component as name
        if name.startswith("git+") or name.startswith("http"):
            name = name.rstrip("/").split("/")[-1].replace(".git", "")
        if not name:
            continue
        deps[name.lower()] = DepEntry(name=name, version=version, raw_line=line.strip(), kind="python")
    return deps


def _diff_requirements(manifest_path: str, old: str, new: str) -> List[DependencyEvent]:
    events: List[DependencyEvent] = []
    
    old_deps = _parse_requirements(Path(manifest_path), old)
    new_deps = _parse_requirements(Path(manifest_path), new)
    
    all_names = set(old_deps.keys()) | set(new_deps.keys())
    for name in sorted(all_names):
        o = old_deps.get(name)
        n = new_deps.get(name)
        
        if o is None and n is not None:
            events.append(DependencyEvent(
                dep_name=n.name, kind="python", manifest_file=manifest_path,
                action="added", version=n.version, raw_line=n.raw_line,
            ))
        elif o is not None and n is None:
            events.append(DependencyEvent(
                dep_name=o.name, kind="python", manifest_file=manifest_path,
                action="removed", version=o.version, raw_line=o.raw_line,
            ))
        elif o and n and o.version != n.version:
            events.append(DependencyEvent(
                dep_name=n.name, kind="python", manifest_file=manifest_path,
                action="changed", version=n.version, raw_line=n.raw_line,
                old_version=o.version, new_version=n.version,
            ))
            
    return events


# ---- pyproject.toml ----

def _parse_pyproject(path: Path, content: str) -> ManifestDict:
    deps: ManifestDict = {}
    try:
        data = tomllib.loads(content)
    except Exception:
        return deps

    # project.dependencies
    for dep in data.get("project", {}).get("dependencies", []):
        dep = dep.strip()
        if not dep:
            continue
        name, ver = _split_req(dep)
        if name:
            deps[name.lower()] = DepEntry(name=name, version=ver, raw_line=dep, kind="python")

    # tool.poetry.dependencies
    poetry = data.get("tool", {}).get("poetry", {})
    for name, spec in poetry.get("dependencies", {}).items():
        if name == "python":
            continue
        ver = spec if isinstance(spec, str) else spec.get("version") if isinstance(spec, dict) else None
        raw = f"{name} = {json.dumps(spec)}"
        deps[name.lower()] = DepEntry(name=name, version=ver, raw_line=raw, kind="python")
    return deps


def _parse_poetry_lock(path: Path, content: str) -> ManifestDict:
    deps: ManifestDict = {}
    try:
        data = tomllib.loads(content)
    except Exception:
        return deps
    for pkg in data.get("package", []):
        name = pkg.get("name", "").lower()
        ver = pkg.get("version")
        if name:
            raw = f'{name} = {{ version = "{ver}" }}'
            deps[name] = DepEntry(name=pkg["name"], version=ver, raw_line=raw, kind="python")
    return deps


# ---- package.json ----

def _parse_package_json(path: Path, content: str) -> ManifestDict:
    deps: ManifestDict = {}
    try:
        data = json.loads(content)
    except Exception:
        return deps
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, ver in data.get(section, {}).items():
            deps[name.lower()] = DepEntry(name=name, version=ver if isinstance(ver, str) else None,
                                          raw_line=f'"{name}": "{ver}"', kind="js")
    return deps


# ---- lock file diff (line-based) ----

LOCK_DEP_LINE_RE = re.compile(
    r"^\s*[\+\-]\s*[\"']?([^\"'@\s:]+)@?[\"']?\s*[:=]\s*[\"']?([^\"',\s]+)[\"']?"
)


def _parse_lock_file(path: Path, content: str) -> ManifestDict:
    """Best-effort extraction of dep@version from lock files (for dict compare)."""
    deps: ManifestDict = {}
    name = path.name.lower()
    for line in content.splitlines():
        m = LOCK_DEP_LINE_RE.match(line)
        if m:
            dep_name = m.group(1)
            ver = m.group(2)
            if dep_name and ver:
                deps[dep_name.lower()] = DepEntry(name=dep_name, version=ver,
                                                   raw_line=line.strip(), kind="lock")
    return deps


def _diff_lock_file(manifest_path: str, old: str, new: str) -> List[DependencyEvent]:
    """Line-diff lock files using unified diff (unified=0).

    Extracts +/- lines that look like dependency entries.
    """
    events: List[DependencyEvent] = []
    # Unified diff with context=0 gives minimal hunks
    # We already have full content; just diff line-by-line
    old_lines = old.splitlines()
    new_lines = new.splitlines()

    old_set = {ln.strip() for ln in old_lines if ln.strip().startswith(("+", "-", " "))}
    # Better: parse both sides with _parse_lock_file and diff dicts
    old_deps = _parse_lock_file(Path(manifest_path), old)
    new_deps = _parse_lock_file(Path(manifest_path), new)
    return _diff_dicts(manifest_path, old_deps, new_deps)


def _diff_dicts(manifest_path: str, old: ManifestDict, new: ManifestDict) -> List[DependencyEvent]:
    events: List[DependencyEvent] = []
    all_names = set(old.keys()) | set(new.keys())
    for name in sorted(all_names):
        o = old.get(name)
        n = new.get(name)
        if o is None and n is not None:
            events.append(DependencyEvent(
                dep_name=n.name, kind=n.kind, manifest_file=manifest_path,
                action="added", version=n.version, raw_line=n.raw_line,
            ))
        elif o is not None and n is None:
            events.append(DependencyEvent(
                dep_name=o.name, kind=o.kind, manifest_file=manifest_path,
                action="removed", version=o.version, raw_line=o.raw_line,
            ))
        elif o and n and o.version != n.version:
            events.append(DependencyEvent(
                dep_name=n.name, kind=n.kind, manifest_file=manifest_path,
                action="changed", version=n.version, raw_line=n.raw_line,
                old_version=o.version, new_version=n.version,
            ))
    return events


def _split_req(req: str) -> Tuple[Optional[str], Optional[str]]:
    """Split 'requests>=2.0' -> ('requests', '>=2.0')."""
    m = re.match(r"^([A-Za-z0-9_.-]+)\s*([=<>~!]=?\s*.+)?$", req.strip())
    if m:
        return m.group(1), m.group(2).strip() if m.group(2) else None
    return None, None