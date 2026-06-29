import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """LLM调用客户端（支持多平台）"""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "mimo")

        configs = {
            "mimo": {
                "api_key": os.getenv("MIMO_API_KEY", ""),
                "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
                "model": "mimo-v2.5",
            },
            "modelscope": {
                "api_key": os.getenv("MODELSCOPE_API_KEY", ""),
                "base_url": "https://api-inference.modelscope.cn/v1",
                "model": "deepseek-ai/DeepSeek-V4-Pro",
            },
        }

        cfg = configs.get(self.provider, configs["mimo"])
        self.client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=30.0)
        self.model = cfg["model"]

    def ask(self, prompt: str, system: str = "", retries: int = 3) -> str:
        """调用LLM，带超时和重试"""
        import time
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    timeout=60.0,
                )
                # 检查响应是否有效
                if not resp or not resp.choices or len(resp.choices) == 0:
                    print(f"[LLM] 返回空响应: {resp}", flush=True)
                    raise ValueError("LLM 返回空响应")
                return resp.choices[0].message.content
            except Exception as e:
                if attempt < retries:
                    print(f"[LLM] 第{attempt+1}次调用失败，{2*(attempt+1)}秒后重试...", flush=True)
                    time.sleep(2 * (attempt + 1))
                else:
                    print(f"[LLM] {retries+1}次调用全部失败: {e}", flush=True)
                    return f"[LLM错误] {e}"

    def answer_choice(self, question: str, options: list[str], is_multi: bool = False) -> str:
        """回答选择题"""
        import re
        n = len(options)
        max_letter = chr(64 + n)  # A=65, so 64+4=D for 4 options

        # 剥离题目文本中已有的选项（避免重复）
        stem = re.split(r'\n?\s*[A-E][.、．]\s', question)[0].strip()
        if len(stem) < 10:
            stem = question

        opt_text = "\n".join([f"{chr(65+i)}. {opt}" for i, opt in enumerate(options)])
        q_type = "多选题" if is_multi else "单选题"
        prompt = f"""你是软件项目管理领域的专家，正在做{q_type}。请仔细分析每个选项后作答。

题目：{stem}

选项：
{opt_text}

【重要】请先逐个分析每个选项为什么对或为什么错，然后给出最终答案。
{"多选题：输出所有正确选项的字母，用逗号分隔" if is_multi else "单选题：只输出一个选项字母"}
最后一行只写字母，不要写其他内容。"""
        print(f"[LLM-debug] options={options}", flush=True)
        print(f"[LLM-debug] opt_text={opt_text[:200]}", flush=True)
        result = self.ask(prompt)
        print(f"[LLM-debug] raw返回: {result[:300]}", flush=True)
        if is_multi:
            letters = [c for c in re.findall(r'[A-E]', result.upper()) if c <= max_letter]
            return ",".join(sorted(set(letters))) if letters else "A"
        else:
            # 取最后一个独立字母行（LLM 先分析再给答案）
            lines = result.strip().split('\n')
            for line in reversed(lines):
                line = line.strip()
                if re.fullmatch(r'[A-E]', line):
                    return line
            # 兜底：取最后一个匹配字母
            matches = [c for c in re.findall(r'[A-E]', result.upper()) if c <= max_letter]
            return matches[-1] if matches else "A"

    def answer_judge(self, question: str) -> str:
        """回答判断题"""
        prompt = f"""请判断以下说法是否正确，只输出"对"或"错"。

{question}
"""
        result = self.ask(prompt)
        if "错" in result[:5] or "错误" in result[:5] or "不正确" in result[:5]:
            return "错"
        return "对"

    def answer_fill(self, question: str) -> str:
        """回答填空题"""
        prompt = f"""请填写以下填空题的答案，只输出答案内容，不要解释。

{question}
"""
        return self.ask(prompt).strip()

    def answer_short(self, question: str) -> str:
        """回答简答题"""
        prompt = f"""请详细回答以下问题，要求条理清晰、内容完整。

{question}
"""
        return self.ask(prompt)

    def answer_code(self, question: str, language: str = "python") -> str:
        """回答编程题"""
        prompt = f"""请用{language}编写以下编程题的代码。
只输出代码，不要解释。代码要能直接运行。

题目：{question}
"""
        result = self.ask(prompt)
        # 提取代码块
        import re
        match = re.search(r'```(?:\w+)?\n(.*?)```', result, re.DOTALL)
        if match:
            return match.group(1).strip()
        return result.strip()

    def answer_paper(self, question: str) -> str:
        """生成论文"""
        prompt = f"""请根据以下要求撰写一篇完整的论文。

要求：
1. 包含标题、摘要、关键词、正文、结论、参考文献
2. 正文至少 2000 字
3. 结构清晰，逻辑严谨
4. 参考文献格式规范
5. 如果有参考材料，请基于材料内容撰写

题目/要求：{question}

请直接输出论文内容，不要包含代码块标记。
"""
        return self.ask(prompt)


# 全局单例
llm = LLMClient()
