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
        self.max_tokens = cfg.get("max_tokens", 8000)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """调用 chat completions，返回文本响应。"""
        logger.debug(f"LLM 调用: model={self.model}, system_len={len(system_prompt)}")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content or ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | list[Any]:
        """调用 LLM 并尝试解析 JSON 响应。"""
        raw = self.chat(system_prompt, user_prompt)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | list[Any]:
        """从 LLM 回复中提取 JSON (支持 markdown code fence 包裹)。"""
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
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到第一个 { 和最后一个 }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start : end + 1])
            raise ValueError(f"无法解析 LLM JSON 响应: {text[:200]}")