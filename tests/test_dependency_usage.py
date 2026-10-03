"""Focused tests for Phase 2 current dependency usage evidence."""

from pathlib import Path

from backend.analysis.dependency_usage import analyze_dependency_usage
from backend.analysis.manifests import DependencyEvent


def _evidence(path: Path, events=()):
    return analyze_dependency_usage(path, events)


def test_python_requirements_manifest(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    result = _evidence(tmp_path)
    assert result[0].dependency_name == "requests"
    assert result[0].declared_version == "2.31.0"
    assert result[0].ecosystem == "python"


def test_python_pyproject_manifest(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["httpx>=0.26"]\n')
    result = _evidence(tmp_path)
    assert result[0].dependency_name == "httpx"
    assert result[0].declared_version == ">=0.26"


def test_python_import_detection_and_normalization(tmp_path):
    (tmp_path / "requirements.txt").write_text("beautifulsoup4==4.12\n")
    (tmp_path / "app.py").write_text("from bs4 import BeautifulSoup\nimport bs4\n")
    result = _evidence(tmp_path)
    assert result[0].current_usage_count == 2
    assert result[0].current_files == ["app.py"]
    assert result[0].current_usage_detected is True


def test_package_json_manifest(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies":{"axios":"^1.0.0"}}')
    result = _evidence(tmp_path)
    assert result[0].dependency_name == "axios"
    assert result[0].declared_version == "^1.0.0"
    assert result[0].ecosystem == "javascript"


def test_javascript_and_typescript_import_detection(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies":{"axios":"^1.0.0"}}')
    (tmp_path / "client.ts").write_text('import axios from "axios";\n')
    (tmp_path / "server.js").write_text('const axios = require("axios");\n')
    result = _evidence(tmp_path)
    assert result[0].current_usage_count == 2
    assert result[0].current_files == ["client.ts", "server.js"]


def test_dependency_with_zero_detected_references(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    result = _evidence(tmp_path)
    assert result[0].current_usage_count == 0
    assert result[0].current_usage_detected is False
    assert result[0].confidence == "medium"


def test_dependency_with_multiple_references_and_history(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    (tmp_path / "one.py").write_text("import requests\n")
    (tmp_path / "two.py").write_text("from requests import get\n")
    event = DependencyEvent(
        dep_name="Requests", kind="python", manifest_file="requirements.txt", action="added",
    )
    result = _evidence(tmp_path, [event])
    assert result[0].current_usage_count == 2
    assert result[0].current_files == ["one.py", "two.py"]
    assert result[0].historical_dependency_events == [event]


def test_malformed_manifests_are_ignored(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project\ndependencies = [")
    (tmp_path / "package.json").write_text("{not json")
    assert _evidence(tmp_path) == []


def test_mixed_python_and_javascript_repository(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\n")
    (tmp_path / "package.json").write_text('{"dependencies":{"axios":"1.0.0"}}')
    (tmp_path / "app.py").write_text("import requests\n")
    (tmp_path / "app.ts").write_text('import axios from "axios"\n')
    result = _evidence(tmp_path)
    assert {(item.dependency_name, item.ecosystem) for item in result} == {
        ("requests", "python"), ("axios", "javascript"),
    }