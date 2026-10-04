"""Run a minimal production-path RepositorySynopsis smoke test."""

import time

from backend.ai.repository_synopsis import RepositorySynopsisClient


EVIDENCE = {
    "repository": {"owner": "o", "name": "r", "url": "u"},
    "default_branch": "main",
    "technologies": [{"name": "Python", "file_count": 1}],
    "structure": ["src/"],
    "representative_history": [{
        "reference": "commit:abc123", "sha": "abc123", "message": "Fix",
    }],
    "allowed_references": ["commit:abc123"],
}


def main() -> None:
    started = time.perf_counter()
    try:
        result = RepositorySynopsisClient().analyze(EVIDENCE)
        print("SYNTHETIC_RESULT=SUCCESS")
        print(f"SYNTHETIC_PURPOSE_LENGTH={len(result.purpose)}")
    except Exception as exc:
        print("SYNTHETIC_RESULT=FAILURE")
        print(f"SYNTHETIC_EXCEPTION={type(exc).__name__}")
        print(f"SYNTHETIC_STATUS={getattr(exc, 'status_code', None)}")
        print(f"SYNTHETIC_CODE={getattr(exc, 'code', None)}")
        print(f"SYNTHETIC_ERROR={str(exc)[:300].replace(chr(10), ' ')}")
    print(f"SYNTHETIC_TIME={time.perf_counter() - started:.3f}s")


if __name__ == "__main__":
    main()
