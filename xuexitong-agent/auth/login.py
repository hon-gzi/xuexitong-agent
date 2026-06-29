import asyncio
from browser.driver import BrowserDriver, CHAOXING_URL, PASSPORT_URL


class AuthManager:
    """学习通登录管理"""

    def __init__(self, driver: BrowserDriver):
        self.driver = driver

    async def login_with_cookie(self) -> bool:
        """用已保存的Cookie登录"""
        loaded = await self.driver.load_cookies()
        if not loaded:
            return False

        await self.driver.page.goto(CHAOXING_URL, wait_until="domcontentloaded", timeout=60000)
        await self.driver.random_delay(2, 4)

        # 检查是否登录成功（看页面上有没有用户信息）
        try:
            await self.driver.page.wait_for_selector(".user-name, .MyHead, #showShort", timeout=8000)
            print("[登录] Cookie有效，自动登录成功")
            return True
        except Exception:
            print("[登录] Cookie已过期，需要重新登录")
            return False

    async def login_with_qrcode(self) -> bool:
        """扫码登录"""
        page = self.driver.page
        await page.goto(PASSPORT_URL, wait_until="domcontentloaded")
        await self.driver.random_delay(1, 2)

        # 切换到扫码登录
        try:
            qr_tab = page.locator("text=扫码登录")
            if await qr_tab.count() > 0:
                await qr_tab.click()
                await self.driver.random_delay(1, 2)
        except Exception:
            pass

        print("\n[登录] 请用学习通APP扫描二维码登录...")
        print("[登录] 扫码后请在手机上确认登录\n")

        # 等待登录成功（URL离开登录页就算成功）
        try:
            # 等待URL不再包含login
            await page.wait_for_url(
                lambda url: "login" not in url and "passport" not in url,
                timeout=120000
            )
            await self.driver.random_delay(2, 3)
            await self.driver.save_cookies()
            print(f"[登录] 扫码登录成功，当前页面: {page.url}")
            print("[登录] Cookie已保存")
            return True
        except Exception:
            # 备用检测：看页面上有没有用户相关元素
            try:
                content = await page.content()
                if "退出" in content or "个人" in content or "我的" in content:
                    await self.driver.save_cookies()
                    print("[登录] 检测到登录状态，Cookie已保存")
                    return True
            except Exception:
                pass
            print("[登录] 扫码超时，请重试")
            return False

    async def login_with_account(self, username: str, password: str) -> bool:
        """账号密码登录"""
        page = self.driver.page
        await page.goto(PASSPORT_URL, wait_until="domcontentloaded")
        await self.driver.random_delay(1, 2)

        # 填写账号密码
        await page.fill("#phone", username)
        await self.driver.random_delay(0.5, 1)
        await page.fill("#pwd", password)
        await self.driver.random_delay(0.5, 1)

        # 点击登录
        await page.click("#loginBtn")
        await self.driver.random_delay(3, 5)

        # 等待页面跳转（离开登录页就算成功）
        try:
            await page.wait_for_url(
                lambda url: "login" not in url and "passport" not in url,
                timeout=15000
            )
            await self.driver.random_delay(2, 3)

            # 关闭可能的弹窗
            try:
                confirm_btn = page.locator("text=确定, text=我知道了, .popup .close, .pu-tips .close").first
                if await confirm_btn.is_visible(timeout=2000):
                    await confirm_btn.click()
            except Exception:
                pass

            await self.driver.save_cookies()
            print(f"[登录] 账号登录成功，当前页面: {page.url}")
            print("[登录] Cookie已保存")
            return True
        except Exception:
            # 备用检测
            try:
                content = await page.content()
                if "退出" in content or "个人" in content or "我的" in content:
                    await self.driver.save_cookies()
                    print("[登录] 检测到登录状态，Cookie已保存")
                    return True
            except Exception:
                pass
            print("[登录] 登录超时，请检查账号密码")
            return False

    async def login(self, method: str = "cookie", **kwargs) -> bool:
        """
        统一登录入口

        method: cookie / qrcode / account
        """
        # 先尝试Cookie登录
        if method == "cookie":
            success = await self.login_with_cookie()
            if success:
                return True
            print("[登录] Cookie无效，切换到扫码登录...")
            method = "qrcode"

        if method == "qrcode":
            return await self.login_with_qrcode()
        elif method == "account":
            return await self.login_with_account(
                kwargs.get("username", ""),
                kwargs.get("password", "")
            )
        return False
