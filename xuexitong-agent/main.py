"""
XuexitongAgent - 学习通智能助手

启动后打开浏览器到登录页面，用户在浏览器中完成登录，自动检测登录成功后注入悬浮聊天窗。

用法：
  python main.py
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

from browser.driver import BrowserDriver
from agent.loop import AgentLoop

PASSPORT_URL = "https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com"


async def wait_for_login(driver: BrowserDriver, timeout: int = 300) -> bool:
    """等待用户在浏览器中完成登录（扫码或密码均可）"""
    page = driver.page
    await page.goto(PASSPORT_URL, wait_until="domcontentloaded", timeout=60000)
    print("[登录] 已打开登录页面，请在浏览器中完成登录...")

    try:
        # 等待 URL 离开登录页（最长等 5 分钟）
        await page.wait_for_url(
            lambda url: "passport2.chaoxing.com" not in url and "login" not in url,
            timeout=timeout * 1000,
        )
        await driver.save_cookies()
        return True
    except Exception:
        # 超时或页面变化，再检查一下是否已经登录
        url = page.url
        if "passport2.chaoxing.com" not in url and "login" not in url:
            await driver.save_cookies()
            return True
        return False


async def main():
    print("""
╔══════════════════════════════════════╗
║     XuexitongAgent - 学习通助手      ║
║                                      ║
║   浏览器中完成登录后自动启动助手      ║
╚══════════════════════════════════════╝
    """)

    headless = os.getenv("HEADLESS", "false").lower() == "true"
    driver = BrowserDriver(headless=headless)

    try:
        print("[启动] 正在打开浏览器...")
        await driver.start()

        # 先尝试 cookie 登录
        from auth.login import AuthManager
        auth = AuthManager(driver)
        success = await auth.login(method="cookie")

        if not success:
            # cookie 失败，打开登录页让用户手动登录
            success = await wait_for_login(driver)

        if not success:
            print("[错误] 登录超时")
            return

        print("[登录] 登录成功！")
        print("[Agent] 正在启动助手...")

        agent = AgentLoop(driver, driver.page)
        await agent.start()

    except KeyboardInterrupt:
        print("\n[退出] 用户中断")
    finally:
        await driver.stop()


if __name__ == "__main__":
    asyncio.run(main())
