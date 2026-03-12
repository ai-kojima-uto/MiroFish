"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客户端"""

    # 已知模型的最大コンテキスト長（トークン数）
    MODEL_CONTEXT_LIMITS = {
        "gpt-4": 8192,
        "gpt-4-0613": 8192,
        "gpt-4-0314": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4-turbo-preview": 128000,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4.1": 1047576,
        "gpt-4.1-mini": 1047576,
        "gpt-4.1-nano": 1047576,
        "gpt-3.5-turbo": 16385,
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _get_context_limit(self) -> int:
        """获取当前模型的上下文长度限制"""
        return self.MODEL_CONTEXT_LIMITS.get(self.model, 128000)

    def _uses_max_completion_tokens(self) -> bool:
        """判断模型是否使用 max_completion_tokens 而非 max_tokens"""
        model = self.model.lower()
        # gpt-5系、o1/o3/o4系は max_completion_tokens を使用
        return (model.startswith("gpt-5") or
                model.startswith("o1") or
                model.startswith("o3") or
                model.startswith("o4"))
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            
        Returns:
            模型响应文本
        """
        # コンテキスト制限の低いモデル（gpt-4等）では max_tokens を自動調整
        context_limit = self._get_context_limit()
        if context_limit <= 8192:
            # メッセージに十分な余裕を持たせるため、コンテキストの1/3を上限とする
            max_tokens = min(max_tokens, context_limit // 3)

        # gpt-5系以降は max_completion_tokens を使用
        # reasoningモデルは内部思考にもトークンを消費するため、上限を4倍に拡大
        is_new_api = self._uses_max_completion_tokens()
        token_param = "max_completion_tokens" if is_new_api else "max_tokens"
        token_value = max_tokens * 4 if is_new_api else max_tokens

        kwargs = {
            "model": self.model,
            "messages": messages,
            token_param: token_value,
        }

        # gpt-5系は temperature=1 のみサポート
        if not is_new_api:
            kwargs["temperature"] = temperature

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
            # response_format removed for GPT-4 compatibility
        )
        # 清理markdown代码块标记
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"LLM返回的JSON格式无效: {cleaned_response}")

