"""
Claude API client wrapper for CORTEX. All Claude calls go through this module.
"""

import logging
from pathlib import Path

import anthropic

from legacy.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
    BEDROCK_MODEL_ID,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL,
    CLAUDE_PROVIDER,
    CLAUDE_TEMPERATURE,
)

logger = logging.getLogger("cortex.claude_client")


class ClaudeClient:
    """
    Wraps the Anthropic SDK for Claude. Uses config defaults; call() allows overrides.
    """

    def __init__(self) -> None:
        """
        Initialise Claude client using either direct Anthropic API credentials
        or AWS Bedrock credentials, based on CLAUDE_PROVIDER.
        """
        self._model = CLAUDE_MODEL

        if CLAUDE_PROVIDER == "bedrock":
            if not hasattr(anthropic, "AnthropicBedrock"):
                raise RuntimeError(
                    "Installed anthropic package does not support Bedrock. "
                    "Please upgrade anthropic to a version that includes AnthropicBedrock."
                )

            bedrock_kwargs: dict[str, str] = {"aws_region": AWS_REGION}
            if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
                bedrock_kwargs["aws_access_key"] = AWS_ACCESS_KEY_ID
                bedrock_kwargs["aws_secret_key"] = AWS_SECRET_ACCESS_KEY
            if AWS_SESSION_TOKEN:
                bedrock_kwargs["aws_session_token"] = AWS_SESSION_TOKEN

            self._client = anthropic.AnthropicBedrock(**bedrock_kwargs)
            self._model = BEDROCK_MODEL_ID
            logger.info("Claude client initialised with AWS Bedrock provider")
            return

        anthropic_kwargs = {"api_key": ANTHROPIC_API_KEY}
        if ANTHROPIC_BASE_URL:
            anthropic_kwargs["base_url"] = ANTHROPIC_BASE_URL
            logger.info("Claude client initialised with Anthropic provider (custom base_url: %s)", ANTHROPIC_BASE_URL)
        else:
            logger.info("Claude client initialised with direct Anthropic provider")
        self._client = anthropic.Anthropic(**anthropic_kwargs)

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Call Claude with the given system and user messages. Uses CLAUDE_MODEL,
        CLAUDE_MAX_TOKENS, CLAUDE_TEMPERATURE from config as defaults; overrides
        if passed. Returns the assistant text response as a plain string.
        """
        tokens = max_tokens if max_tokens is not None else CLAUDE_MAX_TOKENS
        temp = temperature if temperature is not None else CLAUDE_TEMPERATURE
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                temperature=temp,
            )
            if not response.content:
                return ""
            first = response.content[0]
            if hasattr(first, "text"):
                return first.text
            return str(first)
        except anthropic.APIError as e:
            logger.exception("Claude API error")
            raise RuntimeError(f"Claude API call failed: {e}") from e
        except Exception as e:
            logger.exception("Unexpected error calling Claude")
            raise RuntimeError(f"Claude API call failed: {e}") from e

    def load_prompt(self, prompt_name: str) -> str:
        """
        Read and return the content of prompts/{prompt_name}.txt. Raises
        FileNotFoundError with a clear message if the file does not exist.
        """
        path = Path(__file__).resolve().parent.parent / "prompts" / f"{prompt_name}.txt"
        if not path.is_file():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8")
