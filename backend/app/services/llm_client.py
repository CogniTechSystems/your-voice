"""Client for runtimes exposing an OpenAI-compatible chat completions endpoint.

Responses are requested as a server-sent event stream. Long generations, which are common for
reasoning models on local hardware, would otherwise send no data until the whole response is
complete and can be cut off by idle timeouts in the runtime or a proxy in front of it.
"""

import json
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

THINK_BLOCK = re.compile(r"<think>(.*?)(?:</think>|$)", re.DOTALL)
REASONING_FIELDS = ("reasoning_content", "reasoning")
PARAGRAPH_BREAK = "\n\n"
CONNECT_TIMEOUT_SECONDS = 10.0
EVENT_PREFIX = "data:"
END_OF_STREAM = "[DONE]"


class LLMError(RuntimeError):
    """Raised when the runtime returns an error or an unusable response."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Completion:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    reasoning: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class GenerationParameters:
    temperature: float
    top_p: float
    max_tokens: int


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    model: str
    timeout_seconds: float


@dataclass(frozen=True)
class Progress:
    """Partial output of a completion that is still being generated.

    Tool call arguments are the JSON text received so far and are usually incomplete.
    """

    reasoning: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


ProgressCallback = Callable[[Progress], None]


class ChatClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        parameters: GenerationParameters,
        on_progress: ProgressCallback | None = None,
    ) -> Completion: ...


ChatClientFactory = Callable[[Endpoint], ChatClient]


def normalise_base_url(url: str) -> str:
    return url.strip().rstrip("/").removesuffix("/v1")


class OpenAICompatibleClient:
    def __init__(self, endpoint: Endpoint, transport: httpx.BaseTransport | None = None) -> None:
        self._endpoint = endpoint
        self._transport = transport
        self._url = f"{normalise_base_url(endpoint.base_url)}/v1/chat/completions"

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        parameters: GenerationParameters,
        on_progress: ProgressCallback | None = None,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self._endpoint.model,
            "messages": messages,
            "temperature": parameters.temperature,
            "top_p": parameters.top_p,
            "max_tokens": parameters.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        timeout = httpx.Timeout(self._endpoint.timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS)
        try:
            with (
                httpx.Client(transport=self._transport, timeout=timeout) as client,
                client.stream("POST", self._url, json=payload) as response,
            ):
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    raise LLMError(f"Runtime returned HTTP {response.status_code}: {body[:2000]}")
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    return parse_completion(json.loads(response.read()))
                return parse_stream(response.iter_lines(), on_progress)
        except httpx.HTTPError as exc:
            raise LLMError(f"Request to {self._url} failed: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Unexpected response from runtime: {exc}") from exc


def parse_completion(body: dict[str, Any]) -> Completion:
    """Build a completion from a non-streaming response body."""
    message = body["choices"][0]["message"]
    raw_calls = [
        {
            "id": call.get("id"),
            "name": call["function"]["name"],
            "arguments": _arguments_text(call["function"].get("arguments")),
        }
        for call in message.get("tool_calls") or []
    ]
    reported = [message.get(name) for name in REASONING_FIELDS]
    return _build_completion(message.get("content"), reported, raw_calls, body.get("usage"))


def parse_stream(lines: Iterable[str], on_progress: ProgressCallback | None = None) -> Completion:
    """Build a completion from the lines of a server-sent event stream."""
    accumulator = _StreamAccumulator()
    for line in lines:
        if not line.startswith(EVENT_PREFIX):
            continue
        data = line.removeprefix(EVENT_PREFIX).strip()
        if data == END_OF_STREAM:
            break
        chunk = json.loads(data)
        if "error" in chunk:
            raise LLMError(f"Runtime reported an error: {chunk['error']}")
        if accumulator.add(chunk) and on_progress is not None:
            on_progress(accumulator.progress())
    return accumulator.result()


def split_reasoning(content: str | None) -> tuple[str | None, str | None]:
    """Separate inline ``<think>`` blocks from the visible content of a message."""
    if not content or "<think>" not in content:
        return content, None
    reasoning = PARAGRAPH_BREAK.join(block.strip() for block in THINK_BLOCK.findall(content))
    visible = THINK_BLOCK.sub("", content).strip()
    return visible or None, reasoning or None


@dataclass
class _StreamAccumulator:
    content: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    calls: dict[int, dict[str, str | None]] = field(default_factory=dict)
    usage: dict[str, Any] | None = None

    def add(self, chunk: dict[str, Any]) -> bool:
        """Merge one stream chunk and report whether any visible text was added."""
        if chunk.get("usage"):
            self.usage = chunk["usage"]
        changed = False
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                self.content.append(delta["content"])
                changed = True
            for name in REASONING_FIELDS:
                if delta.get(name):
                    self.reasoning.append(delta[name])
                    changed = True
            for call in delta.get("tool_calls") or []:
                self._add_tool_call(call)
                changed = True
        return changed

    def progress(self) -> Progress:
        content, inline_reasoning = split_reasoning("".join(self.content))
        reasoning = [part for part in ("".join(self.reasoning), inline_reasoning) if part]
        calls = tuple(
            ToolCall(
                id=self.calls[index]["id"] or "",
                name=self.calls[index]["name"] or "",
                arguments=self.calls[index]["arguments"] or "",
            )
            for index in sorted(self.calls)
        )
        return Progress(
            reasoning=PARAGRAPH_BREAK.join(reasoning), content=content or "", tool_calls=calls
        )

    def result(self) -> Completion:
        raw_calls = [self.calls[index] for index in sorted(self.calls)]
        return _build_completion(
            "".join(self.content) or None, ["".join(self.reasoning)], raw_calls, self.usage
        )

    def _add_tool_call(self, call: dict[str, Any]) -> None:
        index = call.get("index", len(self.calls))
        entry = self.calls.setdefault(index, {"id": None, "name": "", "arguments": ""})
        function = call.get("function") or {}
        if call.get("id"):
            entry["id"] = call["id"]
        if function.get("name") and not entry["name"]:
            entry["name"] = function["name"]
        if function.get("arguments") is not None:
            entry["arguments"] = (entry["arguments"] or "") + _arguments_text(function["arguments"])


def _build_completion(
    content: str | None,
    reported_reasoning: list[str | None],
    raw_calls: list[dict[str, str | None]],
    usage: dict[str, Any] | None,
) -> Completion:
    visible, inline_reasoning = split_reasoning(content)
    parts = [part.strip() for part in [*reported_reasoning, inline_reasoning] if part]
    tool_calls = tuple(
        ToolCall(
            id=call["id"] or f"call_{uuid.uuid4().hex[:12]}",
            name=call["name"] or "",
            arguments=call["arguments"] or "{}",
        )
        for call in raw_calls
    )
    usage = usage or {}
    return Completion(
        content=visible,
        tool_calls=tool_calls,
        reasoning=PARAGRAPH_BREAK.join(part for part in parts if part) or None,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )


def _arguments_text(arguments: Any) -> str:
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments)
