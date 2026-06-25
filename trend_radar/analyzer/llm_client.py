"""LLM 客户端 — 封装 NewAPI (OpenAI 兼容) 调用。"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from openai import OpenAI

from trend_radar.config import get_config


class LLMClient:
    """通过 NewAPI 调用大模型 (OpenAI 兼容接口)。"""

    def __init__(self) -> None:
        cfg = get_config()["llm"]
        self.client = OpenAI(
            base_url=cfg["api_base"],
            api_key=cfg["api_key"],
        )
        self.model = cfg["model"]
        self.temperature = cfg.get("temperature", 0.7)
        self.max_tokens = cfg.get("max_tokens", 12000)

    def chat(self, system_prompt: str, user_prompt: str, max_retries: int = 2) -> str:
        """调用 chat completions，返回文本响应。失败自动重试。"""
        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"LLM 调用 (attempt {attempt+1}): model={self.model}, system_len={len(system_prompt)}")
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=120,
                )
                content = resp.choices[0].message.content or ""
                if content.strip():
                    return content
                logger.warning(f"LLM 返回空响应 (attempt {attempt+1})")
                if attempt < max_retries:
                    import time
                    time.sleep(3)
            except Exception as e:
                logger.warning(f"LLM 调用失败 (attempt {attempt+1}): {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(3)
                else:
                    raise
        return ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | list[Any]:
        """调用 LLM 并尝试解析 JSON 响应。失败时记录原始返回到日志。"""
        raw = self.chat(system_prompt, user_prompt)
        try:
            return self._parse_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"LLM JSON 解析失败: {e}")
            logger.error(f"LLM 原始返回 (前2000字符): {raw[:2000]}")
            logger.error(f"LLM 原始返回长度: {len(raw)}")
            raise

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | list[Any]:
        """从 LLM 回复中提取 JSON (支持 markdown code fence 包裹 + 容错修复)。"""
        if not text or not text.strip():
            raise ValueError("LLM 返回空响应，无法解析 JSON")

        # 去掉 ```json ... ``` 包裹
        if "```" in text:
            lines = text.split("\n")
            in_code = False
            json_lines = []
            for line in lines:
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code or not json_lines:
                    json_lines.append(line)
            text = "\n".join(json_lines) if json_lines else text

        # 先尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            candidate = text[start : end + 1]
            # 尝试修复常见的 LLM JSON 错误
            # 1. 尾部逗号: {"a": 1,} → {"a": 1}
            import re
            candidate = re.sub(r",\s*}", "}", candidate)
            candidate = re.sub(r",\s*]", "]", candidate)
            # 2. 尝试解析
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            # 3. 如果还是失败，尝试逐层截断 (可能是输出被 max_tokens 截断)
            # 找到最后一个完整的 } 并截断
            for i in range(len(candidate) - 1, 0, -1):
                if candidate[i] == "}":
                    try:
                        # 尝试在当前位置截断并补全
                        truncated = candidate[: i + 1]
                        # 确保括号匹配
                        opens = truncated.count("{")
                        closes = truncated.count("}")
                        if opens > closes:
                            truncated += "}" * (opens - closes)
                        return json.loads(truncated)
                    except json.JSONDecodeError:
                        continue
        raise ValueError(f"无法解析 LLM JSON 响应 (长度={len(text)}, 前200字符): {text[:200]}")