import pytest
from app.schemas.llm_stream import DoneEvent,ErrorEvent,TextDeltaEvent,UsageEvent
from app.services.errors import LLMStreamProtocolError
from app.services.ollama_stream import parse_ollama_stream

def test_parser_converts_text_usage_and_done_events() -> None:
    lines = [
        (
            '{"message":{"role":"assistant","content":"Hel"},'
            '"done":false}'
        ),
             (
            '{"message":{"role":"assistant","content":"lo"},'
            '"done":false}'
        ),
        (
            '{"message":{"role":"assistant","content":""},'
            '"done":true,"done_reason":"stop",'
            '"prompt_eval_count":12,"eval_count":7}'
        ),
    ]
    events = list(parse_ollama_stream(lines))
    assert events ==[
        TextDeltaEvent(text="Hel"),
        TextDeltaEvent(text="lo"),
        UsageEvent(
            input_tokens = 12,
            output_tokens =7,
        ),
        DoneEvent(finish_reason="stop")
    ]
def test_parser_converts_upstream_error_event() -> None:
    events = list(parse_ollama_stream(['{"error":"model not found"}']))
    assert events == [
        ErrorEvent(
            code="OLLAMA_STREAM_ERROR",
            message="model not found",
            retryable=False,
        )
    ]

def test_parser_rejects_invalid_json() -> None:
    with pytest.raises(LLMStreamProtocolError,match="不是合法的JSON"):
        list(parse_ollama_stream(["not-json"]))

def test_parser_rejects_invalid_event_structure() -> None:
    line = (
        '{"message":{"role":"assistant"},'
        '"done":false}'
    )
    with pytest.raises(
    LLMStreamProtocolError,
    match="数据结构不符合预期",
    ):
        list(parse_ollama_stream([line]))