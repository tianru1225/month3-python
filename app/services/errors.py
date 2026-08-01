class LLMUpstreamError(RuntimeError):
    """Raised when the configured LLM upstream request fails."""


class LLMStreamProtocolError(LLMUpstreamError):
    """Raised when an upstream stream event cannot be parsed safely."""