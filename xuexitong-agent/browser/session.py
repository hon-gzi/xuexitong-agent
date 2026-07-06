"""Unified browser session for the Xuexitong agent."""

from typing import Any

from playwright.async_api import Page

from browser.driver import BrowserDriver
from video.player import VideoPlayer
from homework.fetch import HomeworkFetcher
from homework.submit import HomeworkSubmitter

COOKIE_PATH = "data/cookies.json"


class BrowserSession:
    """Manages Playwright lifecycle and provides course operation methods."""

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._driver: BrowserDriver | None = None
        self._player: VideoPlayer | None = None
        self._fetcher: HomeworkFetcher | None = None
        self._submitter: HomeworkSubmitter | None = None

    # ── lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch browser, load cookies for auto-login."""
        self._driver = BrowserDriver(headless=self._headless)
        await self._driver.start()
        await self._driver.load_cookies(COOKIE_PATH)

        self._player = VideoPlayer(self._driver)
        self._fetcher = HomeworkFetcher(self._driver)
        self._submitter = HomeworkSubmitter(self._driver)

    async def stop(self) -> None:
        """Close browser and release resources."""
        if self._driver:
            await self._driver.stop()
        self._driver = None
        self._player = None
        self._fetcher = None
        self._submitter = None

    # ── properties ───────────────────────────────────────────────

    @property
    def page(self) -> Page:
        """Return the current Playwright page."""
        if not self._driver:
            raise RuntimeError("Browser not started — call start() first")
        return self._driver.page

    @property
    def driver(self) -> BrowserDriver:
        """Expose the underlying driver for advanced / compatibility use."""
        if not self._driver:
            raise RuntimeError("Browser not started — call start() first")
        return self._driver

    # ── auth helpers ─────────────────────────────────────────────

    async def ensure_logged_in(self) -> bool:
        """Try loading cookies and navigating to verify login.

        Returns ``True`` if cookies were loaded successfully, ``False`` otherwise.
        The caller (agent) handles re-authentication when this returns ``False``.
        """
        if not self._driver:
            return False
        return await self._driver.load_cookies(COOKIE_PATH)

    async def save_cookies(self) -> None:
        """Persist current session cookies for future sessions."""
        if self._driver:
            await self._driver.save_cookies(COOKIE_PATH)

    # ── course operations (delegated) ────────────────────────────

    async def navigate_to_course(self, course_url: str) -> None:
        """Navigate to a course page."""
        self._require_started()
        await self.page.goto(course_url, wait_until="domcontentloaded", timeout=30000)

    async def get_all_courses(self) -> list[dict]:
        """Return the list of all enrolled courses."""
        self._require_started()
        return await self._player.get_course_list()  # type: ignore[union-attr]

    async def batch_watch_course(
        self,
        course_url: str,
        speed: float = 2.0,
        chapters: list[int] | None = None,
    ) -> dict[str, Any]:
        """Batch-play videos for a course.

        Returns a summary dict with ``total``, ``completed``, ``skipped``,
        ``failed`` keys and a ``results`` list.
        """
        self._require_started()
        return await self._player.batch_watch(  # type: ignore[union-attr]
            course_url, speed=speed, chapters_filter=chapters
        )

    async def screenshot_chapters(self, course_url: str) -> str:
        """Screenshot the chapter list for a course. Returns the file path."""
        self._require_started()
        return await self._player.screenshot_chapter_list(course_url)  # type: ignore[union-attr]

    async def get_assignments(self, course_url: str) -> list[dict]:
        """Return the list of unsubmitted assignments for a course."""
        self._require_started()
        return await self._fetcher.get_assignments(course_url)  # type: ignore[union-attr]

    async def open_assignment(
        self, assignment_url: str, title: str = ""
    ) -> dict[str, Any]:
        """Open an assignment page and return parsed questions."""
        self._require_started()
        return await self._fetcher.open_assignment(assignment_url, title)  # type: ignore[union-attr]

    async def fill_and_submit(
        self,
        questions: list[dict],
        answers: list[str],
        frame: Any | None = None,
    ) -> dict[str, Any]:
        """Fill in answers and submit. Returns a result dict."""
        self._require_started()
        return await self._submitter.fill_and_submit(questions, answers, frame)  # type: ignore[union-attr]

    # ── internal ─────────────────────────────────────────────────

    def _require_started(self) -> None:
        if not self._driver:
            raise RuntimeError("Browser not started — call start() first")
