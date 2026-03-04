import json
import os
from typing import Any, Dict, List, Optional

import openai

from utils import debug


def _strip_markdown_fences(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


class LLMRouter:
    """Central router for all LLM calls.

    Agents call this router through helper functions and do not deal with
    provider/model details directly.
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    def _resolve_model(self, task_type: str = "general") -> str:
        env_by_task = {
            "reasoning": "OPENAI_MODEL_REASONING",
            "creative": "OPENAI_MODEL_CREATIVE",
            "factual": "OPENAI_MODEL_FACTUAL",
            "tool_use": "OPENAI_MODEL_TOOL_USE",
            "general": "OPENAI_MODEL",
        }
        env_name = env_by_task.get(task_type, "OPENAI_MODEL")
        return os.getenv(env_name) or os.getenv("OPENAI_MODEL", "gpt-5")

    def _client(self) -> openai.OpenAI:
        if self.provider != "openai":
            raise ValueError(f"Unsupported LLM_PROVIDER '{self.provider}'. Supported: openai")
        return openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def chat(
        self,
        messages: List[Dict[str, Any]],
        task_type: str = "general",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ):
        client = self._client()
        primary_model = self._resolve_model(task_type)
        fallback_model = os.getenv("OPENAI_FALLBACK_MODEL", "").strip()
        models = [primary_model]
        if fallback_model and fallback_model != primary_model:
            models.append(fallback_model)

        last_exc: Optional[Exception] = None
        for model in models:
            try:
                kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }
                if tools is not None:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice or "auto"

                debug(
                    f"LLM route -> provider={self.provider}, task_type={task_type}, model={model}",
                    prefix="LLM_ROUTER",
                )
                return client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                debug(f"Model call failed for {model}: {exc}", prefix="LLM_ROUTER")

        raise RuntimeError(f"All routed model calls failed: {last_exc}")

    def invoke_json(self, system_prompt: str, user_prompt: str, task_type: str = "reasoning") -> Dict[str, Any]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = self.chat(messages, task_type=task_type)
            raw = response.choices[0].message.content or ""
            if isinstance(raw, list):
                raw = "".join(str(part) for part in raw)
            raw = _strip_markdown_fences(str(raw))
            debug(f"Raw model response: {raw[:420]}", prefix="LLM")
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            debug(f"JSON parse or routed invoke failure: {exc}", prefix="LLM")
            return {}
