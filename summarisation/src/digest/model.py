"""Bedrock Converse calls through an inference profile, with retryable failures separated."""

from __future__ import annotations

import json
import re
from typing import Any

# Failures a later attempt can fix. Anything else (validation, access) is not retried.
RETRYABLE_CODES = {
    "ThrottlingException", "ServiceUnavailableException", "InternalServerException",
    "ModelTimeoutException", "ModelNotReadyException", "ModelErrorException",
    "ProvisionedThroughputExceededException", "RequestLimitExceeded",
}
RETRYABLE_TYPES = {
    "ReadTimeoutError", "ConnectTimeoutError", "EndpointConnectionError", "ConnectionClosedError",
}


class RetryableError(RuntimeError):
    """Raised for throttling and transient service failures; Step Functions retries these."""


class ModelOutputError(ValueError):
    """The model replied, but not with the JSON the prompt asked for."""


def is_retryable(error: Exception) -> bool:
    if isinstance(error, RetryableError):
        return True
    response = getattr(error, "response", None) or {}
    code = str(response.get("Error", {}).get("Code", ""))
    return code in RETRYABLE_CODES or type(error).__name__ in RETRYABLE_TYPES


def parse_json_reply(text: str) -> dict[str, Any]:
    # Models sometimes wrap JSON in a code fence or a sentence; take the outermost object.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ModelOutputError("Model reply contains no JSON object")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise ModelOutputError(f"Model reply is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ModelOutputError("Model reply is not a JSON object")
    return value


class BedrockModel:
    """Use an injected bedrock-runtime client; creating this object makes no requests."""

    def __init__(self, client: Any, inference_profile: str, model_id: str) -> None:
        self.client = client
        self.inference_profile = inference_profile
        self.model_id = model_id

    def complete(self, system: str, prompt: str, *, max_tokens: int = 2048) -> str:
        try:
            response = self.client.converse(
                modelId=self.inference_profile,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
            )
        except Exception as error:
            if is_retryable(error):
                raise RetryableError(f"Bedrock call failed: {error}") from error
            raise
        if response.get("stopReason") == "max_tokens":
            raise ModelOutputError("Model reply was cut off at maxTokens")
        content = response["output"]["message"]["content"]
        return "".join(part.get("text", "") for part in content)
