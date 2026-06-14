"""
OAuth2 Integration Module
=========================
Handles Google and LinkedIn OAuth2 flows, fetches profile data and Gmail
certification signals, and merges everything into data/user_master_profile.json
under the key "automated_external_data".

Environment variables required
-------------------------------
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
LINKEDIN_CLIENT_ID
LINKEDIN_CLIENT_SECRET

Optional
--------
OAUTH_CALLBACK_PORT   (default: 8080)
OAUTH_CALLBACK_TIMEOUT_SEC  (default: 120)

Quick start
-----------
    from integrations.oauth_integrations import DataIntegrator

    integrator = DataIntegrator()
    integrator.run_google()
    integrator.run_linkedin()
    integrator.save()
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from requests_oauthlib import OAuth2Session

# Allow OAuth2 over plain HTTP for localhost only.
# This env var is set inside the module and is never exported.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

logger = logging.getLogger(__name__)

# ── Project paths (resolved relative to this file) ────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR     = _PROJECT_ROOT / "data"
_PROFILE_PATH = _DATA_DIR / "user_master_profile.json"

# ── OAuth endpoints ───────────────────────────────────────────────────────────
_GOOGLE_AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_GOOGLE_SCOPES     = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]
_LINKEDIN_AUTH_URL  = "https://www.linkedin.com/oauth/v2/authorization"
_LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_LINKEDIN_SCOPES    = ["r_liteprofile", "r_emailaddress"]

# Gmail search query — looks for certification/completion emails
_GMAIL_QUERY = (
    'subject:(certification OR diploma OR "completed course" OR '
    '"course completion" OR "certificate of completion")'
)
_GMAIL_MAX_RESULTS = 20

# Keywords to extract from email snippets
_CERT_KEYWORDS = re.compile(
    r"\b(certif\w*|diploma|completed?\s+course|certificate\s+of\s+completion"
    r"|credential|accreditat\w*|badge)\b",
    re.IGNORECASE,
)


# ── Callback HTTP server ───────────────────────────────────────────────────────

class _CallbackServer:
    """
    Minimal FastAPI server that captures a single OAuth callback code.
    Runs in a daemon thread; the calling thread blocks on wait_for_code()
    until the redirect arrives or the timeout expires.
    """

    _SUCCESS_HTML = (
        "<html><head><style>"
        "body{font-family:sans-serif;display:flex;align-items:center;"
        "justify-content:center;height:100vh;background:#f0fdf4;margin:0}"
        "div{text-align:center}</style></head><body><div>"
        "<h2>✅ Authorization successful!</h2>"
        "<p>You can close this tab and return to the terminal.</p>"
        "</div></body></html>"
    )

    def __init__(self, port: int = 8080) -> None:
        self.port        = port
        self._code:  str | None = None
        self._state: str | None = None
        self._event  = threading.Event()
        self._server = None      # set in start()
        self._thread = None

        app = FastAPI(docs_url=None, redoc_url=None)

        @app.get("/callback")
        async def _callback(code: str, state: str = "") -> HTMLResponse:
            self._code  = code
            self._state = state
            self._event.set()
            return HTMLResponse(self._SUCCESS_HTML)

        self._app = app

    def start(self) -> None:
        import uvicorn
        config = uvicorn.Config(
            self._app,
            host="127.0.0.1",
            port=self.port,
            log_level="error",
            loop="none",          # let the thread own its own event loop
        )
        self._server = uvicorn.Server(config)

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._server.serve())
            loop.close()

        self._thread = threading.Thread(target=_run, daemon=True, name="oauth-callback")
        self._thread.start()
        time.sleep(0.6)   # give uvicorn a moment to bind the port

    def wait_for_code(self, timeout: int = 120) -> str:
        if not self._event.wait(timeout=timeout):
            raise TimeoutError(
                f"No OAuth callback received within {timeout}s. "
                "Did you approve the request in the browser?"
            )
        assert self._code is not None
        return self._code

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=3)


# ── Google ────────────────────────────────────────────────────────────────────

def fetch_google_data(
    client_id:     str | None = None,
    client_secret: str | None = None,
    redirect_uri:  str        = "http://localhost:8080/callback",
    port:          int        = 8080,
    timeout:       int        = 120,
) -> dict[str, Any]:
    """
    Run Google OAuth2 flow; return profile info and certification email signals.

    Returns
    -------
    {
        "provider":       "google",
        "fetched_at":     "<ISO timestamp>",
        "profile":        { "id", "name", "given_name", "family_name",
                            "email", "picture", "locale" },
        "certifications": [
            { "subject": "...", "snippet": "...", "date": "...",
              "keywords_found": [...] }
        ]
    }
    """
    cid     = client_id     or os.environ["GOOGLE_CLIENT_ID"]
    csecret = client_secret or os.environ["GOOGLE_CLIENT_SECRET"]

    oauth = OAuth2Session(cid, scope=_GOOGLE_SCOPES, redirect_uri=redirect_uri)
    auth_url, state = oauth.authorization_url(
        _GOOGLE_AUTH_URL,
        access_type="offline",
        prompt="consent",
    )

    server = _CallbackServer(port=port)
    server.start()
    try:
        _open_browser(auth_url)
        code = server.wait_for_code(timeout=timeout)
    finally:
        server.stop()

    token = oauth.fetch_token(
        _GOOGLE_TOKEN_URL,
        code=code,
        client_secret=csecret,
    )

    # ── Profile ───────────────────────────────────────────────────────────────
    profile_resp = oauth.get("https://www.googleapis.com/oauth2/v2/userinfo")
    profile_resp.raise_for_status()
    profile: dict[str, Any] = profile_resp.json()

    # ── Gmail certification signals ───────────────────────────────────────────
    certifications = _scan_gmail_for_certifications(oauth)

    return {
        "provider":       "google",
        "fetched_at":     _now_iso(),
        "profile":        _pick(profile, "id", "name", "given_name", "family_name",
                                "email", "picture", "locale"),
        "certifications": certifications,
    }


def _scan_gmail_for_certifications(
    session: OAuth2Session,
) -> list[dict[str, Any]]:
    """Query Gmail for certification-related emails; return parsed signals."""
    list_resp = session.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        params={"q": _GMAIL_QUERY, "maxResults": _GMAIL_MAX_RESULTS},
    )
    if not list_resp.ok:
        logger.warning("Gmail list failed: %s %s", list_resp.status_code, list_resp.text)
        return []

    messages = list_resp.json().get("messages", [])
    results: list[dict[str, Any]] = []

    for msg in messages:
        detail_resp = session.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
            params={"format": "metadata",
                    "metadataHeaders": ["Subject", "Date", "From"]},
        )
        if not detail_resp.ok:
            continue

        data    = detail_resp.json()
        headers = {h["name"]: h["value"]
                   for h in data.get("payload", {}).get("headers", [])}
        snippet = data.get("snippet", "")

        keywords_found = list({m.group().lower()
                                for m in _CERT_KEYWORDS.finditer(snippet)})
        if not keywords_found:
            # Double-check the subject line
            keywords_found = list({m.group().lower()
                                   for m in _CERT_KEYWORDS.finditer(
                                       headers.get("Subject", ""))})
        if keywords_found:
            results.append({
                "subject":        headers.get("Subject", ""),
                "from":           headers.get("From", ""),
                "date":           headers.get("Date", ""),
                "snippet":        snippet[:300],
                "keywords_found": keywords_found,
            })

    logger.info("Gmail scan: %d certification signal(s) found", len(results))
    return results


# ── LinkedIn ──────────────────────────────────────────────────────────────────

def fetch_linkedin_data(
    client_id:     str | None = None,
    client_secret: str | None = None,
    redirect_uri:  str        = "http://localhost:8080/callback",
    port:          int        = 8080,
    timeout:       int        = 120,
) -> dict[str, Any]:
    """
    Run LinkedIn OAuth2 flow; return basic profile and email address.

    Returns
    -------
    {
        "provider":   "linkedin",
        "fetched_at": "<ISO timestamp>",
        "profile": {
            "id", "first_name", "last_name", "headline",
            "profile_picture_url", "email"
        }
    }
    """
    cid     = client_id     or os.environ["LINKEDIN_CLIENT_ID"]
    csecret = client_secret or os.environ["LINKEDIN_CLIENT_SECRET"]

    oauth = OAuth2Session(cid, scope=_LINKEDIN_SCOPES, redirect_uri=redirect_uri)
    auth_url, state = oauth.authorization_url(_LINKEDIN_AUTH_URL)

    server = _CallbackServer(port=port)
    server.start()
    try:
        _open_browser(auth_url)
        code = server.wait_for_code(timeout=timeout)
    finally:
        server.stop()

    # LinkedIn requires a direct POST with client credentials for token exchange
    token_resp = requests.post(
        _LINKEDIN_TOKEN_URL,
        data={
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  redirect_uri,
            "client_id":     cid,
            "client_secret": csecret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # ── Lite profile ──────────────────────────────────────────────────────────
    profile_resp = requests.get(
        "https://api.linkedin.com/v2/me",
        params={"projection": (
            "(id,localizedFirstName,localizedLastName,"
            "localizedHeadline,profilePicture(displayImage~:playableStreams))"
        )},
        headers=headers,
        timeout=15,
    )
    profile_resp.raise_for_status()
    raw = profile_resp.json()

    # ── Email ─────────────────────────────────────────────────────────────────
    email_resp = requests.get(
        "https://api.linkedin.com/v2/emailAddress",
        params={"q": "members", "projection": "(elements*(handle~))"},
        headers=headers,
        timeout=15,
    )
    email = ""
    if email_resp.ok:
        try:
            email = (email_resp.json()
                     ["elements"][0]["handle~"]["emailAddress"])
        except (KeyError, IndexError):
            pass

    # ── Profile picture URL ───────────────────────────────────────────────────
    picture_url = ""
    try:
        streams = (raw.get("profilePicture", {})
                   .get("displayImage~", {})
                   .get("elements", []))
        if streams:
            picture_url = streams[-1]["identifiers"][0]["identifier"]
    except (KeyError, IndexError):
        pass

    return {
        "provider":   "linkedin",
        "fetched_at": _now_iso(),
        "profile": {
            "id":                  raw.get("id", ""),
            "first_name":          raw.get("localizedFirstName", ""),
            "last_name":           raw.get("localizedLastName", ""),
            "headline":            raw.get("localizedHeadline", ""),
            "profile_picture_url": picture_url,
            "email":               email,
        },
    }


# ── DataIntegrator ────────────────────────────────────────────────────────────

class DataIntegrator:
    """
    Merges Google and LinkedIn OAuth signals into data/user_master_profile.json
    under the key "automated_external_data".

    Usage
    -----
        integrator = DataIntegrator()
        integrator.run_google()    # opens browser, awaits callback, fetches data
        integrator.run_linkedin()  # same for LinkedIn
        integrator.save()          # atomic write to disk
        print(integrator.summary())
    """

    def __init__(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._profile = self._load_profile()
        external = self._profile.setdefault("automated_external_data", {})
        external.setdefault("google",   None)
        external.setdefault("linkedin", None)
        external.setdefault("last_sync", None)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_profile(self) -> dict:
        if _PROFILE_PATH.exists():
            try:
                with _PROFILE_PATH.open(encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load master profile (%s) — creating fresh", exc)
        return {}

    def save(self) -> None:
        """Atomic write: temp file → os.replace → final path."""
        self._profile["automated_external_data"]["last_sync"] = _now_iso()
        self._profile["last_updated"] = _now_iso()
        fd, tmp = tempfile.mkstemp(dir=_DATA_DIR, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._profile, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _PROFILE_PATH)
            logger.info("Master profile saved to %s", _PROFILE_PATH)
        except Exception:
            os.unlink(tmp)
            raise

    # ── Provider runners ──────────────────────────────────────────────────────

    def run_google(
        self,
        client_id:     str | None = None,
        client_secret: str | None = None,
        port:          int        = int(os.getenv("OAUTH_CALLBACK_PORT", "8080")),
        timeout:       int        = int(os.getenv("OAUTH_CALLBACK_TIMEOUT_SEC", "120")),
    ) -> dict[str, Any]:
        """
        Run the Google OAuth2 flow and store the result in the profile.
        Returns the fetched data dict.
        """
        logger.info("Starting Google OAuth2 flow …")
        data = fetch_google_data(
            client_id=client_id,
            client_secret=client_secret,
            port=port,
            timeout=timeout,
        )
        self._profile["automated_external_data"]["google"] = data
        logger.info(
            "Google data fetched: name=%s, certifications=%d",
            data["profile"].get("name", "?"),
            len(data.get("certifications", [])),
        )
        return data

    def run_linkedin(
        self,
        client_id:     str | None = None,
        client_secret: str | None = None,
        port:          int        = int(os.getenv("OAUTH_CALLBACK_PORT", "8080")),
        timeout:       int        = int(os.getenv("OAUTH_CALLBACK_TIMEOUT_SEC", "120")),
    ) -> dict[str, Any]:
        """
        Run the LinkedIn OAuth2 flow and store the result in the profile.
        Returns the fetched data dict.
        """
        logger.info("Starting LinkedIn OAuth2 flow …")
        data = fetch_linkedin_data(
            client_id=client_id,
            client_secret=client_secret,
            port=port,
            timeout=timeout,
        )
        self._profile["automated_external_data"]["linkedin"] = data
        p = data["profile"]
        logger.info("LinkedIn data fetched: %s %s", p.get("first_name"), p.get("last_name"))
        return data

    # ── Inspection ────────────────────────────────────────────────────────────

    def summary(self) -> str:
        ext    = self._profile.get("automated_external_data", {})
        g      = ext.get("google")   or {}
        li     = ext.get("linkedin") or {}
        g_name = g.get("profile", {}).get("name", "—")
        g_cert = len(g.get("certifications", []))
        li_fn  = li.get("profile", {}).get("first_name", "")
        li_ln  = li.get("profile", {}).get("last_name", "")
        li_name = f"{li_fn} {li_ln}".strip() or "—"

        return (
            f"automated_external_data summary\n"
            f"  Google  : {g_name} · {g_cert} certification signal(s)\n"
            f"  LinkedIn: {li_name}\n"
            f"  Saved   : {_PROFILE_PATH}"
        )

    @property
    def external_data(self) -> dict:
        return self._profile.get("automated_external_data", {})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _open_browser(url: str) -> None:
    import webbrowser
    opened = webbrowser.open(url)
    if not opened:
        print(f"\n  Could not open browser automatically. Please visit:\n  {url}\n")
    else:
        print(f"\n  Browser opened for authorization. Waiting for callback …\n")


def _pick(d: dict, *keys: str) -> dict:
    """Return a new dict containing only the requested keys that exist in d."""
    return {k: d[k] for k in keys if k in d}
