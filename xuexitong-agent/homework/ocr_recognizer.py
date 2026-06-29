"""OCR 识别模块 - 截图 + RapidOCR + LLM 智能分析"""

import asyncio
import json
import tempfile
from pathlib import Path
from playwright.async_api import Frame, Page

# OCR 单张图片超时秒数
OCR_TIMEOUT = 30
# 截图超时秒数
SCREENSHOT_TIMEOUT = 15
# 查找容器超时秒数
QUERY_TIMEOUT = 15


class OCRRecognizer:
    """通过截图 + OCR + LLM 识别题目，绕过字体反爬"""

    def __init__(self):
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            print("[OCR] 正在初始化 RapidOCR...", flush=True)
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
            print("[OCR] RapidOCR 初始化完成", flush=True)
        return self._ocr

    async def _query_top_level_containers(self, frame: Frame):
        """查找题目容器，去重：只保留最顶层的，过滤掉被其他容器包含的子元素

        返回 (handles, dom_indices)，dom_indices 是每个容器在原始 querySelectorAll 中的位置
        """
        # 用 JS 在页面端做去重，避免父子重复匹配
        indices = await frame.evaluate("""
            () => {
                const all = document.querySelectorAll(
                    '.questionLi, .singleQuesId, .TiMu, .mark_item, .Zy_TIt6'
                );
                const keep = [];
                for (let i = 0; i < all.length; i++) {
                    let dominated = false;
                    for (let j = 0; j < all.length; j++) {
                        if (i !== j && all[j].contains(all[i])) {
                            dominated = true; break;
                        }
                    }
                    if (!dominated) keep.push(i);
                }
                return keep;
            }
        """)
        # 根据索引拿 handle
        all_handles = await frame.query_selector_all(
            ".questionLi, .singleQuesId, .TiMu, .mark_item, .Zy_TIt6"
        )
        handles = [all_handles[i] for i in indices if i < len(all_handles)]
        return handles, indices

    async def recognize_element(self, element) -> str:
        """识别单个 DOM 元素的文字"""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            await asyncio.wait_for(element.screenshot(path=tmp_path), timeout=SCREENSHOT_TIMEOUT)
            return await asyncio.get_event_loop().run_in_executor(None, self._recognize_image, tmp_path)
        except asyncio.TimeoutError:
            print("[OCR] 截图超时", flush=True)
            return ""
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def recognize_questions(self, frame: Frame) -> list[dict]:
        """识别所有题目，返回结构化数据（每个题带 dom_index 表示在原始 DOM 中的位置）"""
        # 用 JS 去重：只保留最顶层的题目容器，过滤掉被包含的子元素
        print("[OCR] 正在查找题目容器...", flush=True)
        try:
            containers, dom_indices = await asyncio.wait_for(
                self._query_top_level_containers(frame),
                timeout=QUERY_TIMEOUT,
            )
        except asyncio.TimeoutError:
            print("[OCR] 查找容器超时", flush=True)
            containers, dom_indices = [], []

        if not containers:
            print("[OCR] 未找到题目容器", flush=True)
            return []

        print(f"[OCR] 找到 {len(containers)} 个容器，开始截图识别...", flush=True)

        # 收集所有题目区域的截图文本，同时记录 DOM 索引
        all_texts = []
        all_dom_indices = []
        for i, (container, dom_idx) in enumerate(zip(containers, dom_indices)):
            tmp_path = None
            try:
                class_name = await asyncio.wait_for(
                    container.get_attribute("class"), timeout=5
                ) or ""
                if any(skip in class_name.lower() for skip in ["answer", "result", "score", "解析"]):
                    continue

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name

                # 截图（带超时）
                await asyncio.wait_for(container.screenshot(path=tmp_path), timeout=SCREENSHOT_TIMEOUT)

                # OCR 识别（放到线程池避免阻塞，带超时）
                text = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, self._recognize_image, tmp_path),
                    timeout=OCR_TIMEOUT,
                )
                Path(tmp_path).unlink(missing_ok=True)

                print(f"[OCR] 第{i+1}题识别: {len(text or '')} 字符 (DOM索引={dom_idx})", flush=True)

                if text and len(text.strip()) > 10:
                    all_texts.append(text)
                    all_dom_indices.append(dom_idx)
            except asyncio.TimeoutError:
                print(f"[OCR] 第{i+1}题超时，跳过", flush=True)
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)
            except Exception as e:
                print(f"[OCR] 第{i+1}题失败: {e}", flush=True)
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)

        if not all_texts:
            print("[OCR] 所有题目均识别失败", flush=True)
            return []

        print(f"[OCR] 共识别 {len(all_texts)} 道题文本，送 LLM 解析...", flush=True)

        # 用 LLM 智能分析所有题目，传入 DOM 索引
        return await self._llm_parse_questions(all_texts, all_dom_indices)

    def _recognize_image(self, image_path: str) -> str:
        """调用 RapidOCR 识别图片（同步，应在 run_in_executor 中调用）"""
        ocr = self._get_ocr()
        result, _ = ocr(image_path)
        if not result:
            return ""
        lines = [item[1] for item in result]
        return "\n".join(lines)

    async def _llm_parse_questions(self, texts: list[str], dom_indices: list[int] | None = None) -> list[dict]:
        """用 LLM 智能分析 OCR 文本，提取题目和选项"""
        import re
        from llm.client import llm

        # 合并所有文本
        combined_text = "\n\n---\n\n".join(texts)

        prompt = f"""你是学习通答题助手。以下是OCR识别出的试卷文本，每个用"---"分隔，共{len(texts)}段文本，每段对应一道题。

【重要规则】
1. 必须为每一段文本都生成一道题，共{len(texts)}道，不能跳过、合并或省略任何一段
2. 有些文字可能是乱码（字体反爬导致），请根据上下文推测正确内容，无法推测就保留原文
3. 题目和选项可能没有明确分隔，需要你智能判断
4. 每道题必须有题型、题目、选项（选择题）
5. 答案区域（我的答案、正确答案、答案解析）请忽略，只提取题目本身
6. 如果某段文本看起来像答案解析而非题目，仍然尝试从中提取原始题目

请返回JSON数组，必须恰好{len(texts)}个元素，格式如下：
[
  {{
    "index": 0,
    "type": "single",
    "question": "题目内容",
    "options": ["选项A内容", "选项B内容", "选项C内容", "选项D内容"]
  }},
  ...
]

type 可选值: single(单选), multi(多选), judge(判断), fill(填空), short(简答), code(编程), paper(论文/报告)

OCR识别文本：
{combined_text}

重要：只返回JSON数组，恰好{len(texts)}个元素，不要任何其他文字、解释或markdown标记。"""

        print("[OCR] 正在调用 LLM 解析题目...", flush=True)
        # LLM 调用放到线程池，避免阻塞事件循环
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, llm.ask, prompt),
                timeout=120,
            )
        except asyncio.TimeoutError:
            print("[OCR] LLM 调用超时（120s）", flush=True)
            return []
        except Exception as e:
            print(f"[OCR] LLM 调用失败: {type(e).__name__}: {e}", flush=True)
            return []

        if not result:
            print("[OCR] LLM 返回空", flush=True)
            return []

        print(f"[OCR] LLM 返回 {len(result)} 字符", flush=True)

        # 解析JSON
        try:
            # 清理结果，移除可能的markdown标记
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[1] if "\n" in result else result[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

            # 提取JSON部分
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                questions = json.loads(json_match.group())
                # 标准化格式
                for i, q in enumerate(questions):
                    q["index"] = i
                    q["ocr"] = True
                    # 记录在原始 DOM 中的位置，填写答案时要用
                    if dom_indices and i < len(dom_indices):
                        q["dom_index"] = dom_indices[i]
                    # 兼容旧字段名
                    if "question" in q and "text" not in q:
                        q["text"] = q["question"]

                expected = len(texts)
                actual = len(questions)
                if actual < expected:
                    print(f"[OCR] 警告: LLM 只返回 {actual} 道题，期望 {expected} 道，丢失 {expected - actual} 道", flush=True)
                else:
                    print(f"[OCR] LLM 解析成功，{actual} 道题", flush=True)
                return questions
        except Exception as e:
            print(f"[OCR] LLM解析失败: {e}", flush=True)
            print(f"[OCR] 原始返回: {result[:200]}", flush=True)

        return []

    async def recognize_assignments(self, screenshot_path: str) -> list[dict]:
        """从截图中 OCR 识别作业列表，返回未交的作业"""
        import re
        from llm.client import llm

        print(f"[OCR] 识别作业列表截图: {screenshot_path}", flush=True)

        # OCR 识别
        text = await asyncio.get_event_loop().run_in_executor(
            None, self._recognize_image, screenshot_path
        )
        if not text:
            print("[OCR] 作业截图 OCR 识别为空", flush=True)
            return []

        print(f"[OCR] 作业截图 OCR 文本长度: {len(text)}", flush=True)
        print(f"[OCR] OCR 前200字: {text[:200]}", flush=True)

        # 用 LLM 识别作业列表
        prompt = f"""你是学习通作业助手。以下是从作业列表页面截图中 OCR 识别出的文本。

请从中提取需要做的作业。规则如下：

【必须同时满足以下条件才算需要做】
1. 状态是"未交"（不是"已完成""已提交""已批阅""待批阅"）
2. 必须有"剩余XX小时"或"剩余XX天"的时间标记

【以下情况不算需要做】
- 状态是"已完成""已提交""已批阅""待批阅" → 已经处理过了
- 状态是"未交"但没有剩余时间标记 → 过期/截止的作业，不用管

简单说：只返回既有"未交"又有"剩余XX小时/天"的作业。

OCR文本：
{text}

返回格式（只返回JSON数组，不要其他文字）：
[
  {{"title": "作业标题"}},
  ...
]"""

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, llm.ask, prompt),
                timeout=60,
            )
        except Exception as e:
            print(f"[OCR] LLM 识别作业失败: {e}", flush=True)
            return []

        if not result:
            return []

        # 解析 JSON
        try:
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[1] if "\n" in result else result[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                items = json.loads(json_match.group())
                assignments = []
                for item in items:
                    title = item.get("title", "").strip()
                    if title:
                        assignments.append({
                            "title": title,
                            "status": "未交",
                            "done": False,
                            "url": "",
                        })
                print(f"[OCR] 识别到 {len(assignments)} 个活跃未交作业", flush=True)
                return assignments
        except Exception as e:
            print(f"[OCR] 解析作业列表失败: {e}", flush=True)

        return []


async def recognize_page_questions(frame: Frame) -> list[dict]:
    """便捷函数：识别页面中的所有题目"""
    recognizer = OCRRecognizer()
    return await recognizer.recognize_questions(frame)
