import json
import os
import asyncio
import threading
from typing import Dict, Any, Optional

from openai import AsyncOpenAI  # ✅ Use OpenAI-compatible client
from urllib.parse import urlparse, urlunparse

from core.config import CONFIG
from llm_providers.llm_provider import LLMProvider
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("nexa")


class NexaProvider(LLMProvider):
    """Implementation of LLMProvider for Nexa (OpenAI-compatible)."""

    _client_lock = threading.Lock()
    _client: Optional[AsyncOpenAI] = None
    _async_lock = asyncio.Lock()

    @classmethod
    def get_nexa_endpoint(cls) -> str:
        """Get Nexa endpoint from config"""
        logger.debug("Retrieving Nexa endpoint from config")
        provider_config = CONFIG.llm_endpoints.get("nexa")
        if provider_config and provider_config.endpoint:
            endpoint = provider_config.endpoint.strip('"')
            logger.debug(f"Nexa endpoint found: {endpoint}")
            return endpoint
        raise ValueError("Nexa endpoint not found in config")

    @classmethod
    def _normalize_base_url(cls, endpoint: str) -> str:
        """
        Normalize any endpoint string into a base_url suitable for the OpenAI client.

        Examples of acceptable inputs:
        - http://127.0.0.1:8080/v1/chat/completions
        - http://127.0.0.1:8080/v1/
        - http://127.0.0.1:8080/v1
        - http://127.0.0.1:8080/
        - http://127.0.0.1:8080

        Desired outputs:
        - http://127.0.0.1:8080/v1   (if original path contains /v1)
        - http://127.0.0.1:8080      (if no /v1 appears)
        """
        p = urlparse(endpoint.strip())

        # Build scheme://netloc
        netloc = p.netloc or p.path  # if user passed something without scheme, fallback
        scheme = p.scheme or "http"

        # Ensure we have something valid in netloc; if not, try to parse differently
        if not netloc:
            # If someone supplied e.g. "127.0.0.1:8080/v1/..." as endpoint (no scheme)
            tmp = urlparse("http://" + endpoint.strip())
            scheme = tmp.scheme
            netloc = tmp.netloc
            p = tmp

        # Find '/v1' in the path (first occurrence). If found, base path should be '/v1'
        path = ""
        if p.path:
            # Use a regex-safe check for path segment '/v1'
            if "/v1" in p.path:
                path = "/v1"
            else:
                # if no /v1, don't include any path (keep root)
                path = ""
        else:
            path = ""

        normalized = urlunparse((scheme, netloc, path, "", "", ""))
        # Remove trailing slash if any (we prefer no trailing slash in base_url)
        normalized = normalized.rstrip("/")
        return normalized


    @classmethod
    def get_client(cls) -> AsyncOpenAI:
        """Get or create Nexa async client with normalized base_url."""
        with cls._client_lock:
            if cls._client is None:
                raw_endpoint = cls.get_nexa_endpoint()  # e.g. might be 'http://127.0.0.1:8080/v1/chat/completions'
                base_url = cls._normalize_base_url(raw_endpoint)

                logger.info(f"Initializing Nexa AsyncOpenAI client at base_url={base_url}")
                # Use AsyncOpenAI for async; if you prefer sync use OpenAI(...)
                cls._client = AsyncOpenAI(base_url=base_url, api_key="not-needed")

        return cls._client

    @classmethod
    def clean_response(cls, content: str) -> Dict[str, Any]:
        """Clean and parse Nexa JSON response"""
        content = content.strip().replace("```json", "").replace("```", "").strip()
        start, end = content.find("{"), content.rfind("}") + 1
        if start == -1 or end <= 0:
            logger.error("No valid JSON object found in response")
            return {}
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response as JSON: {e}")
            return {}

    async def get_completion(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 60.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Get structured JSON completion from Nexa"""
        provider_config = CONFIG.llm_endpoints.get("nexa")
        model = model or (provider_config.models.high if provider_config else "llama3")

        system_prompt = (
            "You are a helpful assistant that provides responses in JSON format. "
            f"Your response must be valid JSON that matches this schema: {json.dumps(schema)}. "
            "Only output the JSON object, no explanations."
        )

        client = self.get_client()

        async with self._async_lock:
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    timeout=timeout,
                )
                content = response.choices[0].message.content
                logger.debug(f"Nexa response: {content[:200]}...")
                return self.clean_response(content)
            except asyncio.TimeoutError:
                logger.error(f"Nexa request timed out after {timeout}s")
                return {}
            except Exception:
                logger.exception("Nexa completion failed")
                raise

# ✅ Singleton for convenience
provider = NexaProvider()
get_nexa_completion = provider.get_completion
