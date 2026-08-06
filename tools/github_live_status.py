from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(slots=True)
class GitHubLiveStatusPublisher:
    """Publish a small JSON status document through GitHub's contents API.

    The publisher is intentionally best-effort: search work must never fail merely
    because GitHub is temporarily unavailable. Updates are throttled to avoid
    creating an excessive number of commits during long campaigns.
    """

    path: str = "reports/live-search-status.json"
    min_interval_seconds: float = 60.0
    repository: str | None = None
    branch: str | None = None
    token: str | None = None
    _last_publish: float = 0.0
    _last_payload: str | None = None

    def __post_init__(self) -> None:
        self.repository = self.repository or os.environ.get("GITHUB_REPOSITORY")
        self.branch = self.branch or os.environ.get("OM_LIVE_STATUS_BRANCH") or os.environ.get("GITHUB_REF_NAME")
        self.token = self.token or os.environ.get("OM_LIVE_STATUS_TOKEN") or os.environ.get("GITHUB_TOKEN")

    @property
    def enabled(self) -> bool:
        return bool(self.repository and self.branch and self.token)

    def publish(self, payload: dict[str, Any], *, force: bool = False) -> bool:
        if not self.enabled:
            return False
        now = monotonic()
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if not force and now - self._last_publish < self.min_interval_seconds:
            return False
        if not force and serialized == self._last_payload:
            return False

        try:
            sha = self._remote_sha()
            body: dict[str, Any] = {
                "message": f"Update live OMSIM status: {payload.get('stage', 'research')}",
                "content": base64.b64encode((json.dumps(payload, indent=2) + "\n").encode("utf-8")).decode("ascii"),
                "branch": self.branch,
            }
            if sha:
                body["sha"] = sha
            self._request("PUT", self._contents_url(), body)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            print(f"live-status publish skipped: {exc}", flush=True)
            return False

        self._last_publish = now
        self._last_payload = serialized
        return True

    def _contents_url(self) -> str:
        assert self.repository
        return f"https://api.github.com/repos/{self.repository}/contents/{quote(self.path)}"

    def _remote_sha(self) -> str | None:
        try:
            response = self._request("GET", f"{self._contents_url()}?ref={quote(str(self.branch))}")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        value = response.get("sha")
        return str(value) if value else None

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.token
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "omsim-local-research-worker",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=20) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}
