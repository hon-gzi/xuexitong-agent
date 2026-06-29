import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# 学习通域名
CHAOXING_URL = "https://chaoxing.com"
PASSPORT_URL = "https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com"
MOOC_API = "https://mooc1-api.chaoxing.com"


class BrowserDriver:
    """Playwright 浏览器封装"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> Page:
        """启动浏览器，返回页面对象"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        self._page = await self._context.new_page()
        return self._page

    async def stop(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("浏览器未启动，先调用 start()")
        return self._page

    async def save_cookies(self, path: str = "data/cookies.json"):
        """保存Cookie到文件"""
        import json, os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cookies = await self._context.cookies()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    async def load_cookies(self, path: str = "data/cookies.json") -> bool:
        """从文件加载Cookie"""
        import json, os
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        await self._context.add_cookies(cookies)
        return True

    async def wait_for_navigation(self, timeout: int = 10000):
        """等待页面加载"""
        await self.page.wait_for_load_state("networkidle", timeout=timeout)

    async def random_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """随机延迟，模拟真人操作"""
        import random
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)
