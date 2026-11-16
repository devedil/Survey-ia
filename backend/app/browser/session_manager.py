from __future__ import annotations

import ipaddress
import re
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TypeVar
from urllib.parse import urlsplit

from backend.app.browser.schemas import BrowserControlRead
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    Route,
    sync_playwright,
)

TEST_SITE_PATH = "/api/v1/browser/test-site"
_CONTROL_SELECTOR = "input, textarea, select"
_INSPECTION_SCRIPT = """
elements => {
  const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
  const labelFor = element => {
    const labels = element.labels ? Array.from(element.labels).map(label => clean(label.innerText)) : [];
    return clean(labels.filter(Boolean).join(' '));
  };
  const elementsWithIndexes = elements.map((element, index) => ({element, index}));
  const groups = new Map();
  const supportedTypes = new Set([
    'text', 'search', 'email', 'tel', 'url', 'number', 'date', 'month',
    'week', 'time', 'datetime-local', 'radio', 'checkbox'
  ]);
  for (const item of elementsWithIndexes) {
    const element = item.element;
    const tag = element.tagName.toLowerCase();
    const type = tag === 'textarea' ? 'textarea' : tag === 'select'
      ? 'select' : (element.getAttribute('type') || 'text').toLowerCase();
    if (tag === 'input' && !supportedTypes.has(type)) continue;
    if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') continue;
    const fieldset = element.closest('fieldset');
    const legend = fieldset ? clean(fieldset.querySelector('legend')?.innerText) : '';
    const formIndex = element.form ? Array.from(document.forms).indexOf(element.form) : -1;
    const fieldsetIndex = fieldset ? Array.from(document.querySelectorAll('fieldset')).indexOf(fieldset) : -1;
    const isGroup = type === 'radio' || type === 'checkbox';
    const groupKey = isGroup && element.name
      ? `${type}:${formIndex}:${fieldsetIndex}:${element.name}`
      : `element:${item.index}`;
    if (!groups.has(groupKey)) {
      const question = legend || (isGroup
        ? clean(element.getAttribute('aria-label') || element.name || element.id)
        : labelFor(element) || clean(
          element.getAttribute('aria-label') || element.getAttribute('placeholder') ||
          element.name || element.id
        ));
      groups.set(groupKey, {
        type,
        question,
        required: false,
        max_length: null,
        indices: [],
        options: [],
        signature: []
      });
    }
    const group = groups.get(groupKey);
    group.indices.push(item.index);
    group.required = group.required || element.required;
    if (element.maxLength > 0) group.max_length = element.maxLength;
    group.signature.push([
      type,
      element.name || '',
      element.id || '',
      legend,
      element.getAttribute('aria-label') || ''
    ]);
    if (type === 'select') {
      group.options = Array.from(element.options)
        .filter(option => !option.disabled && option.value !== '')
        .map(option => ({label: clean(option.label), value: option.value}));
    } else if (isGroup) {
      group.options.push({
        label: labelFor(element) || clean(element.getAttribute('aria-label') || element.value),
        value: element.value
      });
    }
  }
  return Array.from(groups.values()).map((group, index) => ({
    control_id: `control-${index}`,
    question_text: group.question,
    control_type: group.type,
    required: group.required,
    max_length: group.max_length,
    options: group.options,
    indices: group.indices,
    signature: JSON.stringify(group.signature)
  }));
}
"""
_CAPTCHA_SELECTORS = (
    'iframe[src*="recaptcha" i]',
    'iframe[src*="hcaptcha" i]',
    '[class*="g-recaptcha" i]',
    '[class*="h-captcha" i]',
    '[id*="captcha" i]',
    '[name*="captcha" i]',
)
_TEXT_INPUT_TYPES = {
    "text",
    "search",
    "email",
    "tel",
    "url",
    "number",
    "date",
    "month",
    "week",
    "time",
    "datetime-local",
    "textarea",
}
_Result = TypeVar("_Result")


class BrowserSessionError(ValueError):
    pass


class BrowserDependencyError(RuntimeError):
    pass


class BrowserPolicyError(BrowserSessionError):
    def __init__(self, message: str, domain: str | None = None):
        super().__init__(message)
        self.domain = domain


class BrowserSessionNotFound(BrowserSessionError):
    pass


@dataclass
class _Control:
    control_id: str
    question_text: str
    control_type: str
    required: bool
    max_length: int | None
    indices: list[int]
    options: list[dict[str, str]]
    signature: str

    def read(self) -> BrowserControlRead:
        return BrowserControlRead(
            control_id=self.control_id,
            question_text=self.question_text,
            control_type=self.control_type,
            options=[option["label"] for option in self.options],
            required=self.required,
            max_length=self.max_length,
        )


@dataclass
class _BrowserSession:
    session_id: str
    profile_id: str
    created_at: datetime
    context: BrowserContext | None = None
    page: Page | None = None
    status: str = "active"
    current_url: str | None = None
    blocked_domain: str | None = None
    controls: dict[str, _Control] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


class BrowserSessionManager:
    def __init__(self, allowed_origins: str):
        self._allowed_origins = self._parse_allowed_origins(allowed_origins)
        self._sessions: dict[str, _BrowserSession] = {}
        self._sessions_lock = threading.RLock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser-session")
        self._worker_ident: int | None = None
        self._closed = False

    def _call_on_browser_thread(
        self,
        operation: Callable[..., _Result],
        *args: object,
    ) -> _Result:
        if self._closed:
            raise BrowserSessionError("Browser session manager is closed")
        if threading.get_ident() == self._worker_ident:
            return operation(*args)
        return self._executor.submit(self._run_on_browser_thread, operation, args).result()

    def _run_on_browser_thread(
        self,
        operation: Callable[..., _Result],
        args: tuple[object, ...],
    ) -> _Result:
        self._worker_ident = threading.get_ident()
        return operation(*args)

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int] | None:
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            if (
                parsed.scheme not in {"http", "https"}
                or not host
                or parsed.username is not None
                or parsed.password is not None
            ):
                return None
            normalized_host = host.casefold().rstrip(".")
            try:
                is_loopback = normalized_host == "localhost" or ipaddress.ip_address(
                    normalized_host
                ).is_loopback
            except ValueError:
                is_loopback = False
            if not is_loopback:
                return None
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return parsed.scheme, normalized_host, port
        except ValueError:
            return None

    @classmethod
    def _parse_allowed_origins(cls, allowed_origins: str) -> set[tuple[str, str, int]]:
        origins: set[tuple[str, str, int]] = set()
        for configured in allowed_origins.split(","):
            value = configured.strip()
            if not value:
                continue
            parsed = urlsplit(value)
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("BROWSER_ALLOWED_ORIGINS must contain origins without paths")
            origin = cls._origin(value)
            if origin is None:
                raise ValueError("Browser origins must use HTTP(S) and a loopback host")
            origins.add(origin)
        if not origins:
            raise ValueError("At least one loopback browser origin must be configured")
        return origins

    @staticmethod
    def domain_for_url(url: str) -> str | None:
        try:
            return urlsplit(url).hostname
        except ValueError:
            return None

    def _is_allowed_url(self, url: str, *, resource: bool = False) -> bool:
        origin = self._origin(url)
        if origin is None or origin not in self._allowed_origins:
            return False
        try:
            parsed = urlsplit(url)
        except ValueError:
            return False
        if parsed.query or parsed.fragment:
            return False
        allowed_paths = {TEST_SITE_PATH, f"{TEST_SITE_PATH}/"}
        if resource:
            allowed_paths.add("/favicon.ico")
        return parsed.path in allowed_paths

    def _get_session(self, session_id: str) -> _BrowserSession:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise BrowserSessionNotFound("Browser session not found")
        return session

    def _active_session(self, session_id: str) -> _BrowserSession:
        session = self._get_session(session_id)
        if session.status != "active" or session.page is None:
            raise BrowserSessionError(f"Browser session is {session.status}")
        return session

    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except PlaywrightError as error:
            self._playwright.stop()
            self._playwright = None
            raise BrowserDependencyError(
                "Chromium is unavailable; run `python -m playwright install chromium`"
            ) from error

    def create(self, profile_id: str) -> _BrowserSession:
        return self._call_on_browser_thread(self._create, profile_id)

    def _create(self, profile_id: str) -> _BrowserSession:
        self._ensure_browser()
        if self._browser is None:
            raise BrowserDependencyError("Chromium could not be started")
        session_id = str(uuid.uuid4())
        session = _BrowserSession(
            session_id=session_id,
            profile_id=profile_id,
            created_at=datetime.now(timezone.utc),
        )
        try:
            session.context = self._browser.new_context(
                accept_downloads=False,
                service_workers="block",
            )
            session.page = session.context.new_page()
            session.page.set_default_timeout(5000)

            def guard_request(route: Route) -> None:
                request_url = route.request.url
                if (
                    route.request.method not in {"GET", "HEAD"}
                    or not self._is_allowed_url(request_url, resource=True)
                ):
                    session.blocked_domain = self.domain_for_url(request_url)
                    session.status = "blocked"
                    route.abort(error_code="blockedbyclient")
                    return
                route.continue_()

            session.context.route("**/*", guard_request)
            session.page.on("popup", lambda popup: popup.close())
        except PlaywrightError as error:
            if session.context is not None:
                session.context.close()
            raise BrowserSessionError("Browser session could not be created") from error
        with self._sessions_lock:
            self._sessions[session_id] = session
        return session

    def navigate(self, session_id: str, url: str) -> _BrowserSession:
        return self._call_on_browser_thread(self._navigate, session_id, url)

    def _navigate(self, session_id: str, url: str) -> _BrowserSession:
        session = self._active_session(session_id)
        with session.lock:
            if not self._is_allowed_url(url):
                self._block(session, self.domain_for_url(url))
                raise BrowserPolicyError(
                    "Navigation is outside the local test-site allowlist",
                    self.domain_for_url(url),
                )
            try:
                session.page.goto(url, wait_until="domcontentloaded")
            except PlaywrightError as error:
                if session.status == "blocked":
                    self._close_context(session)
                    raise BrowserPolicyError(
                        "A request attempted to leave the local test-site allowlist",
                        session.blocked_domain,
                    ) from error
                raise BrowserSessionError("Browser navigation failed") from error
            if not self._is_allowed_url(session.page.url):
                domain = self.domain_for_url(session.page.url)
                self._block(session, domain)
                raise BrowserPolicyError("Navigation ended outside the local test-site allowlist", domain)
            session.current_url = session.page.url
            session.controls.clear()
            return session

    def inspect(self, session_id: str) -> tuple[_BrowserSession, str, list[BrowserControlRead]]:
        return self._call_on_browser_thread(self._inspect, session_id)

    def _inspect(self, session_id: str) -> tuple[_BrowserSession, str, list[BrowserControlRead]]:
        session = self._active_session(session_id)
        with session.lock:
            if not session.current_url:
                raise BrowserSessionError("Navigate to the local test site before inspection")
            try:
                has_captcha_element = any(
                    session.page.locator(selector).count() for selector in _CAPTCHA_SELECTORS
                )
                has_captcha_text = bool(
                    re.search(
                        r"\b(?:captcha|recaptcha|hcaptcha)\b",
                        session.page.locator("body").inner_text(),
                        re.IGNORECASE,
                    )
                )
            except PlaywrightError as error:
                raise BrowserSessionError("The page could not be inspected") from error
            if has_captcha_element or has_captcha_text:
                domain = self.domain_for_url(session.current_url)
                self._block(session, domain)
                raise BrowserPolicyError("CAPTCHA detected; the browser session was stopped", domain)
            try:
                raw_controls = session.page.locator(_CONTROL_SELECTOR).evaluate_all(_INSPECTION_SCRIPT)
                title = session.page.title()
            except PlaywrightError as error:
                raise BrowserSessionError("The page could not be inspected") from error
            session.controls = {
                raw["control_id"]: _Control(
                    control_id=raw["control_id"],
                    question_text=raw["question_text"],
                    control_type=raw["control_type"],
                    required=raw["required"],
                    max_length=raw["max_length"],
                    indices=raw["indices"],
                    options=raw["options"],
                    signature=raw["signature"],
                )
                for raw in raw_controls
            }
            return (
                session,
                title,
                [control.read() for control in session.controls.values()],
            )

    def control_for_proposal(self, session_id: str, control_id: str) -> tuple[_BrowserSession, _Control]:
        return self._call_on_browser_thread(
            self._control_for_proposal,
            session_id,
            control_id,
        )

    def _control_for_proposal(self, session_id: str, control_id: str) -> tuple[_BrowserSession, _Control]:
        session = self._active_session(session_id)
        control = session.controls.get(control_id)
        if control is None:
            raise BrowserSessionError("Inspect the current page and select one of its controls")
        if not control.question_text:
            raise BrowserSessionError("This control has no accessible question label")
        return session, control

    def fill_approved(self, session_id: str, control_id: str, answer: str) -> _BrowserSession:
        return self._call_on_browser_thread(
            self._fill_approved,
            session_id,
            control_id,
            answer,
        )

    def _fill_approved(self, session_id: str, control_id: str, answer: str) -> _BrowserSession:
        try:
            return self._fill_control(session_id, control_id, answer)
        except PlaywrightError as error:
            raise BrowserSessionError("The browser could not safely fill and verify this control") from error

    def _fill_control(self, session_id: str, control_id: str, answer: str) -> _BrowserSession:
        session, control = self.control_for_proposal(session_id, control_id)
        with session.lock:
            self.inspect(session_id)
            current = session.controls.get(control_id)
            if current is None or current.signature != control.signature:
                raise BrowserSessionError("The inspected form changed; inspect it again before filling")
            if not answer or len(answer) > 10000:
                raise BrowserSessionError("The approved answer is empty or too long")
            locators = session.page.locator(_CONTROL_SELECTOR)
            if control.control_type in _TEXT_INPUT_TYPES:
                if len(control.indices) != 1:
                    raise BrowserSessionError("This text control no longer maps to a single field")
                locator = locators.nth(control.indices[0])
                is_writable = locator.evaluate("element => !element.disabled && !element.readOnly")
                if not is_writable:
                    raise BrowserSessionError("The target field is disabled or read-only")
                if control.max_length is not None and len(answer) > control.max_length:
                    raise BrowserSessionError("The approved answer exceeds the field's maximum length")
                locator.fill(answer)
                if locator.input_value() != answer:
                    locator.fill("")
                    raise BrowserSessionError("The value entered did not match the approved answer")
                return session

            if control.control_type == "select":
                option = self._matching_option(control, answer)
                locator = locators.nth(control.indices[0])
                locator.select_option(label=option["label"])
                selected_label = re.sub(
                    r"\s+",
                    " ",
                    locator.locator("option:checked").inner_text(),
                ).strip()
                if selected_label != option["label"]:
                    raise BrowserSessionError("The selected option did not match the approved answer")
                return session

            if control.control_type == "radio":
                option = self._matching_option(control, answer)
                index = control.options.index(option)
                locator = locators.nth(control.indices[index])
                locator.check()
                if not locator.is_checked():
                    raise BrowserSessionError("The selected option did not match the approved answer")
                return session

            if control.control_type == "checkbox":
                selected = self._matching_checkbox_options(control, answer)
                selected_indexes = {control.options.index(option) for option in selected}
                for option_index, element_index in enumerate(control.indices):
                    locator = locators.nth(element_index)
                    if option_index in selected_indexes:
                        locator.check()
                    else:
                        locator.uncheck()
                actual = [
                    option["label"]
                    for option_index, option in enumerate(control.options)
                    if locators.nth(control.indices[option_index]).is_checked()
                ]
                if len(actual) != len(selected) or set(actual) != {
                    option["label"] for option in selected
                }:
                    raise BrowserSessionError("The selected options did not match the approved answer")
                return session
            raise BrowserSessionError("This control type cannot be filled safely")

    @staticmethod
    def _matching_option(control: _Control, answer: str) -> dict[str, str]:
        matches = [
            option for option in control.options
            if option["label"].strip() == answer.strip()
        ]
        if len(matches) != 1:
            raise BrowserSessionError("The approved answer must exactly match one available option")
        return matches[0]

    @classmethod
    def _matching_checkbox_options(cls, control: _Control, answer: str) -> list[dict[str, str]]:
        exact_match = [
            option for option in control.options
            if option["label"].strip() == answer.strip()
        ]
        if exact_match:
            if len(exact_match) != 1:
                raise BrowserSessionError("The approved answer matches ambiguous checkbox options")
            return exact_match
        labels = [label.strip() for label in re.split(r"[,;\n]", answer) if label.strip()]
        if not labels:
            raise BrowserSessionError("The approved answer does not select any checkbox options")
        selected = [cls._matching_option(control, label) for label in labels]
        if len({option["value"] for option in selected}) != len(selected):
            raise BrowserSessionError("The approved answer repeats a checkbox option")
        return selected

    def status(self, session_id: str) -> _BrowserSession:
        return self._call_on_browser_thread(self._status, session_id)

    def _status(self, session_id: str) -> _BrowserSession:
        session = self._get_session(session_id)
        if session.status == "blocked" and session.context is not None:
            with session.lock:
                self._close_context(session)
        return session

    def stop(self, session_id: str) -> _BrowserSession:
        return self._call_on_browser_thread(self._stop, session_id)

    def _stop(self, session_id: str) -> _BrowserSession:
        session = self._get_session(session_id)
        with session.lock:
            if session.status == "active":
                session.status = "stopped"
            self._close_context(session)
        return session

    def _block(self, session: _BrowserSession, domain: str | None) -> None:
        session.status = "blocked"
        session.blocked_domain = domain
        self._close_context(session)

    @staticmethod
    def _close_context(session: _BrowserSession) -> None:
        if session.context is not None:
            session.context.close()
            session.context = None
            session.page = None
        session.controls.clear()

    def close_all(self) -> None:
        if self._closed:
            return
        self._call_on_browser_thread(self._close_all)
        self._executor.shutdown(wait=True)
        self._closed = True

    def _close_all(self) -> None:
        with self._sessions_lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            with session.lock:
                self._close_context(session)
                if session.status == "active":
                    session.status = "stopped"
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None


def public_session(session: _BrowserSession) -> dict:
    current_url = None
    if session.current_url:
        parsed = urlsplit(session.current_url)
        current_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return {
        "session_id": session.session_id,
        "profile_id": session.profile_id,
        "status": session.status,
        "current_url": current_url,
        "created_at": session.created_at,
    }
