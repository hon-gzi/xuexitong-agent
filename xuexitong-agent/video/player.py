import asyncio
import re
from browser.driver import BrowserDriver, CHAOXING_URL


class VideoPlayer:
    """学习通视频播放控制"""

    def __init__(self, driver: BrowserDriver):
        self.driver = driver
        self.is_playing = False

    async def get_course_list(self) -> list[dict]:
        """获取所有课程列表"""
        page = self.driver.page

        await page.goto("https://mooc2-ans.chaoxing.com/visit/courses/list",
                        wait_until="domcontentloaded", timeout=30000)
        await self.driver.random_delay(4, 6)

        courses = await page.evaluate("""
            () => {
                const results = [];
                const links = document.querySelectorAll('a[href*="courseid"]');
                const seen = new Set();
                for (const a of links) {
                    const text = a.innerText.trim();
                    if (text.length > 3 && text.length < 100 && !seen.has(text)) {
                        seen.add(text);
                        results.push({name: text.substring(0, 60), url: a.href});
                    }
                }
                return results;
            }
        """)

        print(f"[课程] 获取到 {len(courses)} 门课程")
        return courses

    async def get_chapters(self, course_url: str) -> list[dict]:
        """获取课程的所有章节及其完成状态。

        使用课程目录页（studentcourse）的 icon class 判断完成状态：
        - openlock: 无任务的章节（学习导航、章节测试题等），视为已完成
        - orange: 有未完成任务的章节（视频任务点），需要处理
        - blank (title="闯关模式发放"): 闯关模式章节，需要处理
        """
        page = self.driver.page

        if not course_url:
            print("[章节] 课程URL为空")
            return []

        # 访问课程页面
        print(f"[章节] 正在访问课程...")
        await page.goto(course_url, wait_until="domcontentloaded", timeout=30000)
        print(f"[章节] 跳转后URL: {page.url[:120]}")
        await self.driver.random_delay(5, 8)

        # 点击"章节"标签
        print("[章节] 点击'章节'标签...")
        clicked = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('li, a, span');
                for (const el of els) {
                    if (el.innerText.trim() === '章节' && el.offsetParent !== null) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        if clicked:
            print("[章节] 已点击'章节'标签")
        else:
            print("[章节] 未找到'章节'标签")

        await self.driver.random_delay(8, 12)

        # 找到包含章节内容的frame（URL包含studentcourse的frame）
        target_frame = None
        for frame in page.frames:
            if "studentcourse" in frame.url:
                target_frame = frame
                print(f"[章节] 找到章节frame: {frame.url[:80]}")
                break

        if not target_frame:
            # 备用：找li数量最多的frame
            max_li = 0
            for frame in page.frames:
                try:
                    count = await frame.evaluate("document.querySelectorAll('li').length")
                    if count > max_li:
                        max_li = count
                        target_frame = frame
                except Exception:
                    continue
            if target_frame:
                print(f"[章节] 备用方案，li最多的frame: {target_frame.url[:80]} ({max_li}个li)")

        if not target_frame:
            print("[章节] 未找到章节内容所在的frame")
            return []

        # 提取章节列表（从 chapter_item 提取，通过 catalog_state 检测完成状态）
        raw = await target_frame.evaluate("""
            () => {
                const chapters = [];
                const items = document.querySelectorAll('.chapter_item[onclick*="toOld"]');

                for (const item of items) {
                    const onclick = item.getAttribute('onclick') || '';
                    const match = onclick.match(/toOld\\('([^']+)'\\s*,\\s*'([^']+)'\\s*,\\s*'([^']+)'\\s*,\\s*(\\d+)/);
                    if (!match) continue;

                    const courseId = match[1];
                    const chapterId = match[2];
                    const clazzid = match[3];
                    const cpi = parseInt(match[4]);

                    // 获取章节标题
                    const titleEl = item.querySelector('.catalog_name span[title], .catalog_name span');
                    const title = titleEl ? (titleEl.getAttribute('title') || titleEl.textContent.trim()) : '';

                    // 获取章节号
                    const sbarEl = item.querySelector('.catalog_sbar');
                    const chapterNum = sbarEl ? sbarEl.textContent.trim() : '';

                    // 检测完成状态：
                    // 有 catalog_state class → 已完成（无待完成任务）
                    // 无 catalog_state class → 待完成（有任务点待完成）
                    const stateEl = item.querySelector('.catalog_state');
                    const completed = !!stateEl;

                    // 获取任务点数
                    const jobInput = item.querySelector('.knowledgeJobCount');
                    const jobCount = jobInput ? parseInt(jobInput.value) : 0;

                    // 获取提示文本
                    const tipEl = item.querySelector('.bntHoverTips');
                    const tip = tipEl ? tipEl.textContent.trim() : '';

                    chapters.push({
                        courseId: courseId,
                        chapterId: chapterId,
                        clazzid: clazzid,
                        cpi: cpi,
                        title: (chapterNum ? chapterNum + ' ' : '') + title,
                        completed: completed,
                        iconType: completed ? 'finished' : 'pending',
                        jobCount: jobCount,
                        tip: tip,
                    });
                }
                return chapters;
            }
        """)

        chapters = []
        for item in raw:
            chapters.append({
                "courseId": item["courseId"],
                "chapterId": item["chapterId"],
                "clazzid": item["clazzid"],
                "cpi": item["cpi"],
                "title": item["title"].strip(),
                "completed": item.get("completed", False),
                "iconType": item.get("iconType", "unknown"),
                "jobCount": item.get("jobCount", 0),
                "tip": item.get("tip", ""),
                "frame": target_frame,
            })

        # 统计
        completed_count = sum(1 for ch in chapters if ch["completed"])
        pending_count = sum(1 for ch in chapters if not ch["completed"])
        print(f"[章节] 获取到 {len(chapters)} 个章节: {completed_count} 个已完成, {pending_count} 个待处理")
        for ch in chapters[:10]:
            status = "DONE" if ch["completed"] else "TODO"
            print(f"  [{status}] {ch['title']}")
        if len(chapters) > 10:
            print(f"  ... 共 {len(chapters)} 个")

        return chapters

    async def check_section_completed(self, chapter: dict) -> bool:
        """检查单个章节的实际完成状态（通过学习页面的ans-job-finished判断）。

        对于有任务的章节，进入学习页面检查 ans-job-finished class。
        """
        page = self.driver.page
        chapter_id = chapter.get("chapterId", "")
        course_id = chapter.get("courseId", "")
        clazz_id = chapter.get("clazzid", "")

        if not chapter_id or not course_id:
            return chapter.get("completed", False)

        # 构造学习页面URL（使用 mooc2-ans 域名）
        url = (
            f"https://mooc2-ans.chaoxing.com/mooc-ans/mycourse/studentstudy"
            f"?chapterId={chapter_id}"
            f"&courseId={course_id}"
            f"&clazzid={clazz_id}"
        )

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self.driver.random_delay(4, 6)

            # 在knowledge/cards frame中检查 ans-job-finished
            for frame in page.frames:
                try:
                    result = await frame.evaluate("""() => {
                        const jobIcons = document.querySelectorAll('.ans-job-icon');
                        const jobFinished = document.querySelectorAll('.ans-job-finished');
                        return {
                            total: jobIcons.length,
                            finished: jobFinished.length,
                            allComplete: jobIcons.length > 0 && jobIcons.length === jobFinished.length,
                            noJobs: jobIcons.length === 0
                        };
                    }""")
                    if result and (result.get("total", 0) > 0 or result.get("noJobs")):
                        return result["allComplete"] or result["noJobs"]
                except Exception:
                    continue

            # 没找到任务元素，返回原始状态
            return chapter.get("completed", False)
        except Exception as e:
            print(f"[检测] 检查章节完成状态失败: {e}")
            return chapter.get("completed", False)

    async def screenshot_chapter_list(self, course_url: str) -> str:
        """截取章节列表区域的截图，返回文件路径"""
        page = self.driver.page

        # 导航到课程页
        await page.goto(course_url, wait_until="domcontentloaded", timeout=30000)
        await self.driver.random_delay(5, 8)

        # 点击章节标签
        await page.evaluate("""
            () => {
                const els = document.querySelectorAll('li, a, span');
                for (const el of els) {
                    if (el.innerText.trim() === '章节' && el.offsetParent !== null) {
                        el.click(); return true;
                    }
                }
                return false;
            }
        """)
        await self.driver.random_delay(5, 8)

        # 找chapter frame
        frame = None
        for f in page.frames:
            if "studentcourse" in f.url:
                frame = f
                break

        if not frame:
            print("[截图] 未找到章节frame，截全页")
            path = "data/chapter_list.png"
            await page.screenshot(path=path)
            return path

        # 获取章节列表容器的位置和大小，截取该区域
        try:
            rect = await frame.evaluate("""
                () => {
                    const el = document.querySelector('.chapter_body, .chapter_td, .course_chapter');
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return {x: r.x, y: r.y, width: r.width, height: r.height};
                }
            """)
        except Exception:
            rect = None

        path = "data/chapter_list.png"
        if rect and rect["width"] > 0 and rect["height"] > 0:
            # 截取frame中章节列表区域
            # frame的坐标需要加上frame在页面中的偏移
            try:
                frame_box = await frame.evaluate("""
                    () => {
                        // 找到iframe元素获取其在页面中的位置
                        const iframe = window.frameElement;
                        if (!iframe) return null;
                        const r = iframe.getBoundingClientRect();
                        return {x: r.x, y: r.y};
                    }
                """)
            except Exception:
                frame_box = None

            if frame_box:
                clip = {
                    "x": frame_box["x"] + rect["x"],
                    "y": frame_box["y"] + rect["y"],
                    "width": min(rect["width"], 400),
                    "height": min(rect["height"], 700),
                }
                await page.screenshot(path=path, clip=clip)
            else:
                # fallback: 截全页
                await page.screenshot(path=path)
        else:
            await page.screenshot(path=path)

        print(f"[截图] 章节列表截图已保存: {path}")
        return path

    async def play_video(self, chapter: dict, speed: float = 2.0) -> dict:
        """播放指定章节的视频"""
        page = self.driver.page
        frame = chapter.get("frame")
        title = chapter.get("title", "")

        # 在frame中通过toOld()点击章节
        print(f"[播放] 点击章节: {title[:40]}")
        try:
            if frame:
                await frame.evaluate(f"""
                    () => {{ toOld('{chapter["courseId"]}', '{chapter["chapterId"]}', '{chapter["clazzid"]}', {chapter["cpi"]}); }}
                """)
        except Exception as e:
            return {"status": "failed", "error": f"点击章节失败: {e}"}

        # 点击后页面会跳转到新URL，等待加载
        await self.driver.random_delay(8, 12)

        # 等待页面body加载完成
        page = self.driver.page
        for _ in range(5):
            body_len = await page.evaluate("document.body ? document.body.innerHTML.length : 0")
            if body_len > 500:
                break
            await self.driver.random_delay(3, 5)

        # 委托给 _handle_current_chapter 处理（支持多内容块）
        return await self._handle_current_chapter(speed)

    async def _detect_content_type(self) -> str:
        """检测当前页面的内容类型"""
        page = self.driver.page

        for _ in range(3):
            for frame in page.frames:
                try:
                    url = frame.url.lower()
                    if ".pdf" in url or "modules/pdf" in url:
                        return "pdf"
                    if "ppt" in url:
                        return "ppt"
                    if await frame.evaluate("!!document.querySelector('video')"):
                        return "video"
                except Exception:
                    continue
            await self.driver.random_delay(2, 3)

        # 检查是否有图片内容
        try:
            has_image = await page.evaluate("!!document.querySelector('.image_wrap, .img_pic')")
            if has_image:
                return "image"
        except Exception:
            pass

        return "unknown"

    async def _find_video_frame(self):
        """在所有frame中查找视频元素"""
        page = self.driver.page
        for _ in range(5):
            for frame in page.frames:
                try:
                    has_video = await frame.evaluate("!!document.querySelector('video')")
                    if has_video:
                        return frame
                except Exception:
                    continue
            await self.driver.random_delay(2, 3)
        return None

    async def _mark_as_done(self):
        """标记章节为已完成（等待一段时间让系统记录）"""
        await self.driver.random_delay(3, 5)

    async def _wait_for_completion(self, frame, speed: float) -> dict:
        """等待视频播放完成"""
        import time
        start_time = time.time()
        check_count = 0
        consecutive_errors = 0

        while True:
            try:
                progress = await frame.evaluate("""
                    () => {
                        const v = document.querySelector('video');
                        if (!v) return {error: 'no video'};
                        return {
                            current: v.currentTime,
                            duration: v.duration,
                            ended: v.ended,
                            paused: v.paused,
                            percent: (v.currentTime / v.duration * 100).toFixed(1)
                        };
                    }
                """)
                consecutive_errors = 0

                if progress.get("error"):
                    return {"status": "failed", "error": "视频元素丢失"}

                if progress.get("ended"):
                    elapsed = time.time() - start_time
                    print(f"[播放] 视频播放完成，耗时: {elapsed:.0f}秒")
                    return {"status": "completed", "duration": elapsed}

                # 如果暂停了，重新播放
                if progress.get("paused"):
                    try:
                        await frame.evaluate("document.querySelector('video').play()")
                    except Exception:
                        pass

                check_count += 1
                if check_count % 6 == 0:
                    print(f"[播放] 进度: {progress.get('percent', 0)}%")

                # 检测弹窗
                await self._handle_popups()

            except Exception as e:
                consecutive_errors += 1
                err_str = str(e)
                # frame detached → 尝试重新找视频frame
                if "detached" in err_str.lower():
                    print(f"[播放] Frame已分离，尝试重新查找视频...")
                    new_frame = await self._find_video_frame()
                    if new_frame:
                        frame = new_frame
                        # 恢复倍速
                        try:
                            await frame.evaluate(f"document.querySelector('video').playbackRate = {speed}")
                            await frame.evaluate("document.querySelector('video').play()")
                        except Exception:
                            pass
                        consecutive_errors = 0
                        continue
                    else:
                        print("[播放] 无法重新找到视频frame")
                        return {"status": "failed", "error": "视频frame丢失"}

                if consecutive_errors >= 10:
                    return {"status": "failed", "error": f"连续异常: {err_str[:80]}"}

            await asyncio.sleep(5)

    async def _handle_popups(self):
        """处理学习过程中的弹窗（只关闭视频相关的遮罩弹窗）"""
        page = self.driver.page

        # 只处理视频播放器相关的弹窗，避免点击页面级确认按钮导致导航
        popup_selectors = [
            "text=继续观看",
            ".ans-job-tip .ans-job-tip-btn",
            ".popDiv .close",
            ".maskDiv .close",
            ".popup .close",
            ".pu-tips .close",
            ".el-dialog__headerbtn",
        ]
        for selector in popup_selectors:
            try:
                el = page.locator(selector).first
                await el.wait_for(state="visible", timeout=500)
                await el.click()
                print(f"[弹窗] 已关闭: {selector}")
                await self.driver.random_delay(0.5, 1)
            except Exception:
                continue

    async def batch_watch(self, course_url: str, speed: float = 2.0, chapters_filter: list[int] = None) -> dict:
        """批量刷完指定章节的视频。chapters_filter为章节序号列表（从0开始），None则刷全部。"""
        chapters = await self.get_chapters(course_url)
        if not chapters:
            print("[批量] 未获取到章节")
            return {"total": 0, "completed": 0, "skipped": 0, "failed": 0, "results": []}

        # 如果指定了过滤列表，只处理这些章节
        if chapters_filter is not None:
            chapters = [chapters[i] for i in chapters_filter if i < len(chapters)]
            print(f"\n[批量] 过滤后 {len(chapters)} 个章节待处理\n")
        else:
            # 只处理未完成的章节
            pending = [ch for ch in chapters if not ch.get("completed", False)]
            print(f"\n[批量] 共 {len(chapters)} 个章节, 其中 {len(pending)} 个待处理\n")
            chapters = pending

        results = []
        page = self.driver.page

        for i, ch in enumerate(chapters):
            title = ch.get("title", "未知章节")
            course_id = ch["courseId"]
            chapter_id = ch["chapterId"]
            clazz_id = ch["clazzid"]
            cpi = ch["cpi"]

            print(f"\n[批量] === 第 {i+1}/{len(chapters)} 个: {title} ===")

            # 导航回课程页 + 点击章节标签，最多重试2次
            nav_ok = False
            for attempt in range(3):
                try:
                    await page.goto(course_url, wait_until="domcontentloaded", timeout=30000)
                    await self.driver.random_delay(5, 8)
                    await page.evaluate("""
                        () => {
                            const els = document.querySelectorAll('li, a, span');
                            for (const el of els) {
                                if (el.innerText.trim() === '章节' && el.offsetParent !== null) {
                                    el.click(); return true;
                                }
                            }
                            return false;
                        }
                    """)
                    await self.driver.random_delay(5, 8)
                    nav_ok = True
                    break
                except Exception as e:
                    print(f"[批量] 导航回课程页失败(尝试{attempt+1}/3): {e}")
                    if attempt < 2:
                        await self.driver.random_delay(3, 5)
            if not nav_ok:
                results.append({"chapter": title, "status": "failed", "error": "导航课程页失败"})
                continue

            # 找chapter frame
            frame = None
            for f in page.frames:
                if "studentcourse" in f.url:
                    frame = f
                    break
            if not frame:
                print("[批量] 未找到章节frame")
                results.append({"chapter": title, "status": "failed", "error": "未找到章节frame"})
                break

            # 通过toOld()打开章节
            try:
                await frame.evaluate(f"""
                    () => {{ toOld('{course_id}', '{chapter_id}', '{clazz_id}', {cpi}); }}
                """)
            except Exception as e:
                print(f"[批量] 点击章节失败: {e}")
                results.append({"chapter": title, "status": "failed", "error": str(e)})
                continue

            await self.driver.random_delay(8, 12)

            # 处理章节内容（播放视频/跳过非视频）
            result = await self._handle_current_chapter(speed)
            results.append({"chapter": title, **result})
            await self.driver.random_delay(3, 5)

        completed = sum(1 for r in results if r.get("status") == "completed")
        skipped = sum(1 for r in results if r.get("status") == "skipped")
        failed = sum(1 for r in results if r.get("status") == "failed")
        print(f"\n[批量] 完成! {completed}个视频播放, {skipped}个已跳过, {failed}个失败")
        return {"total": len(results), "completed": completed, "skipped": skipped, "failed": failed, "results": results}

    async def _get_current_chapter_title(self) -> str:
        """获取当前章节标题"""
        page = self.driver.page
        try:
            title = await page.evaluate("""
                () => {
                    const el = document.querySelector('.prev_title, .posCatalog_name.active, h1, .title, .chapterTitle');
                    return el ? el.innerText.trim().substring(0, 60) : '未知章节';
                }
            """)
            return title if title else "未知章节"
        except Exception:
            return "未知章节"

    async def _handle_current_chapter(self, speed: float) -> dict:
        """处理当前章节：遍历页面内所有内容块（视频/PDF/文档等）"""
        page = self.driver.page

        # 关闭可能的弹窗
        await self._handle_popups()

        # 等待内容加载（最多30秒）
        for _ in range(15):
            body_len = await page.evaluate("document.body ? document.body.innerHTML.length : 0")
            frame_count = len(page.frames)
            if body_len > 5000 and frame_count > 3:
                break
            await self._handle_popups()
            await self.driver.random_delay(2, 3)

        # 扫描所有 frame，收集内容块
        processed_frames = set()
        total_processed = 0
        max_rounds = 5  # 最多处理5轮（防止无限循环）

        for round_num in range(max_rounds):
            content_items = await self._scan_content_items(exclude=processed_frames)
            if not content_items:
                break

            print(f"[播放] 第{round_num+1}轮，发现 {len(content_items)} 个内容块")
            round_handled = False

            for item in content_items:
                frame_url = item["url"]
                ctype = item["type"]
                frame = item["frame"]

                if frame_url in processed_frames:
                    continue

                print(f"[播放] 处理: [{ctype}] {frame_url[:60]}")

                if ctype == "video":
                    try:
                        await frame.evaluate(f"""
                            () => {{
                                const v = document.querySelector('video');
                                if (v) {{ v.playbackRate = {speed}; v.play(); }}
                            }}
                        """)
                        print(f"[播放] 视频开始播放，倍速: {speed}x")
                        self.is_playing = True
                        result = await self._wait_for_completion(frame, speed)
                        self.is_playing = False
                        print(f"[播放] 视频结果: {result.get('status')}")
                        processed_frames.add(frame_url)
                        round_handled = True
                        total_processed += 1
                    except Exception as e:
                        print(f"[播放] 视频播放失败: {e}")
                        processed_frames.add(frame_url)

                elif ctype == "pdf":
                    print(f"[播放] PDF内容，等待加载...")
                    await self._mark_as_done()
                    processed_frames.add(frame_url)
                    round_handled = True
                    total_processed += 1

                elif ctype == "ppt":
                    print(f"[播放] PPT内容，等待加载...")
                    await self._mark_as_done()
                    processed_frames.add(frame_url)
                    round_handled = True
                    total_processed += 1

                elif ctype == "image":
                    print(f"[播放] 图片内容，跳过")
                    processed_frames.add(frame_url)
                    round_handled = True
                    total_processed += 1

                else:
                    print(f"[播放] 未知类型({ctype})，跳过")
                    processed_frames.add(frame_url)

            if not round_handled:
                break

            # 等待可能的新内容加载
            await self.driver.random_delay(2, 3)
            await self._handle_popups()

        if total_processed == 0:
            return {"status": "skipped", "reason": "未找到可处理的内容"}

        return {"status": "completed", "processed": total_processed}

    async def _scan_content_items(self, exclude: set = None) -> list[dict]:
        """扫描所有 frame，返回内容块列表（去重）"""
        page = self.driver.page
        if exclude is None:
            exclude = set()
        items = []

        for frame in page.frames:
            try:
                frame_url = frame.url
                if frame_url in exclude or not frame_url or frame_url == "about:blank":
                    continue

                url_lower = frame_url.lower()
                if ".pdf" in url_lower or "modules/pdf" in url_lower:
                    items.append({"type": "pdf", "url": frame_url, "frame": frame})
                elif "ppt" in url_lower:
                    items.append({"type": "ppt", "url": frame_url, "frame": frame})
                elif await frame.evaluate("!!document.querySelector('video')"):
                    items.append({"type": "video", "url": frame_url, "frame": frame})
                elif await frame.evaluate("!!document.querySelector('.image_wrap, .img_pic')"):
                    items.append({"type": "image", "url": frame_url, "frame": frame})
            except Exception:
                continue

        return items

