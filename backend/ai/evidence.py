"""Deterministic, focused evidence package construction for decision analysis."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional

from backend.analysis.dependency_usage import DependencyUsageEvidence, analyze_dependency_usage
from backend.analysis.git_repo import GitRepository


@dataclass
class EvidencePackage:
    target: str
    dependency: Optional[dict]
    dependency_events: List[dict]
    commits: List[dict]
    file_changes: List[dict]
    manifest_diffs: List[dict]
    allowed_references: List[str]

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "dependency": self.dependency,
            "dependency_events": self.dependency_events,
            "commits": self.commits,
            "file_changes": self.file_changes,
            "manifest_diffs": self.manifest_diffs,
            "allowed_references": self.allowed_references,
        }


def build_evidence_package(
    repo_root: Path,
    dependency_name: str,
    dependency_events: Iterable[Any],
    commits: Iterable[Any],
    file_changes: Iterable[Any],
    commit_lookup: Optional[dict[str, Any]] = None,
    selected_commit_hash: Optional[str] = None,
) -> EvidencePackage:
    usage = analyze_dependency_usage(repo_root)
    selected = next((item for item in usage if item.dependency_name.lower() == dependency_name.lower()), None)
    matching_events = [event for event in dependency_events if event.dep_name.lower() == dependency_name.lower()]
    if selected_commit_hash:
        matching_events = [event for event in matching_events if event.commit_hash == selected_commit_hash]
    event_hashes = {event.commit_hash for event in matching_events}

    relevant_commits = [
        commit for commit in commits
        if commit.hash in event_hashes
        or (selected_commit_hash is None and commit.change_type == "dependency")
    ]
    relevant_hashes = {commit.hash for commit in relevant_commits}
    relevant_changes = [change for change in file_changes if change.commit_hash in relevant_hashes]
    manifest_diffs = _manifest_diffs(repo_root, matching_events, commit_lookup or {}, selected_commit_hash)

    dependency_dict = _usage_dict(selected) if selected else None
    event_dicts = [_event_dict(event) for event in matching_events]
    commit_dicts = [_commit_dict(commit) for commit in relevant_commits]
    change_dicts = [_change_dict(change) for change in relevant_changes]
    allowed = [f"dependency:{dependency_name}"]
    allowed.extend(f"dependency_event:{event.commit_hash}:{event.dep_name}:{event.action}" for event in matching_events)
    allowed.extend(f"commit:{commit.hash}" for commit in relevant_commits)
    allowed.extend(f"file_change:{change.commit_hash}:{change.path}" for change in relevant_changes)
    if selected:
        allowed.extend(f"current_usage:{path}" for path in selected.current_files)

    return EvidencePackage(
        target=dependency_name,
        dependency=dependency_dict,
        dependency_events=event_dicts,
        commits=commit_dicts,
        file_changes=change_dicts,
        manifest_diffs=manifest_diffs,
        allowed_references=allowed,
    )


def _usage_dict(item: DependencyUsageEvidence) -> dict:
    return {
        "dependency_name": item.dependency_name,
        "ecosystem": item.ecosystem,
        "manifest_file": item.manifest_file,
        "declared_version": item.declared_version,
        "current_usage_count": item.current_usage_count,
        "current_files": item.current_files,
        "current_usage_detected": item.current_usage_detected,
        "confidence": item.confidence,
    }


def _event_dict(event: Any) -> dict:
    return {
        "reference": f"dependency_event:{event.commit_hash}:{event.dep_name}:{event.action}",
        "dependency_name": event.dep_name,
        "kind": event.kind,
        "manifest_file": event.manifest_file,
        "action": event.action,
        "version": event.version,
        "commit_hash": event.commit_hash,
        "old_version": event.old_version,
        "new_version": event.new_version,
    }


def _commit_dict(commit: Any) -> dict:
    return {
        "reference": f"commit:{commit.hash}",
        "hash": commit.hash,
        "timestamp": commit.timestamp.isoformat(),
        "message": commit.message,
        "change_type": commit.change_type,
    }


def _change_dict(change: Any) -> dict:
    return {
        "reference": f"file_change:{change.commit_hash}:{change.path}",
        "commit_hash": change.commit_hash,
        "path": change.path,
        "status": change.status,
        "additions": change.additions,
        "deletions": change.deletions,
    }


def _manifest_diffs(repo_root: Path, events: List[Any], commit_lookup: dict, selected_hash: Optional[str]) -> List[dict]:
    repo = GitRepository(repo_root) if (repo_root / ".git").exists() else None
    if repo is None:
        return []
    results = []
    for event in events:
        if selected_hash and event.commit_hash != selected_hash:
            continue
        commit = commit_lookup.get(event.commit_hash)
        if not commit or not commit.parents:
            continue
        try:
            diff = repo.diff_manifest(commit.parents[0], commit.hash, event.manifest_file)
        except Exception:
            continue
        if diff:
            results.append({"commit_hash": commit.hash, "manifest_file": event.manifest_file, "diff": diff[:12000]})
    return results