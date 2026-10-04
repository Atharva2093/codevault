"""Small bounded public GitHub API client."""

import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, field_validator


MAX_GITHUB_ISSUES = 20
MAX_ISSUE_BODY = 4000


class GitHubError(Exception):
    pass


class GitHubIssue(BaseModel):
    number: int = Field(ge=1)
    title: str
    body: str = ""
    state: str
    labels: list[str] = Field(default_factory=list)
    author: str = "Unknown"
    created_at: datetime
    updated_at: datetime
    comments: int = Field(ge=0)
    html_url: str

    @field_validator("html_url")
    @classmethod
    def validate_github_url(cls, value: str) -> str:
        if not value.startswith("https://github.com/"):
            raise ValueError("issue URL must point to GitHub")
        return value


def fetch_open_issues(owner: str, name: str) -> list[GitHubIssue]:
    url = f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(name, safe='')}/issues?state=open&per_page={MAX_GITHUB_ISSUES}"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "CausalCode"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        if exc.code == 429 or exc.code == 403:
            raise GitHubError("GitHub API rate limit or access error") from exc
        raise GitHubError("GitHub API request failed") from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise GitHubError("GitHub API unavailable") from exc
    if not isinstance(payload, list):
        raise GitHubError("GitHub returned an invalid issue response")
    issues = []
    for item in payload:
        if not isinstance(item, dict) or "pull_request" in item:
            continue
        try:
            issues.append(GitHubIssue(
                number=item["number"], title=item["title"], body=(item.get("body") or "")[:MAX_ISSUE_BODY],
                state=item["state"], labels=[label["name"] for label in item.get("labels", []) if isinstance(label, dict) and "name" in label],
                author=(item.get("user") or {}).get("login", "Unknown"), created_at=item["created_at"],
                updated_at=item["updated_at"], comments=item.get("comments", 0), html_url=item["html_url"],
            ))
        except (KeyError, TypeError, ValueError):
            raise GitHubError("GitHub returned malformed issue data")
    return issues[:MAX_GITHUB_ISSUES]