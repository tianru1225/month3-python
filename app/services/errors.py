class LLMUpstreamError(RuntimeError):
    code: str = "LLM_UPSTREAM_ERROR"
    public_message: str = "LLM upstream request failed"
    http_status: int = 502
    retryable: bool = False


class LLMRateLimitError(LLMUpstreamError):
    code = "LLM_RATE_LIMITED"
    public_message = "LLM upstream rate limit exceeded"
    http_status = 429
    retryable = True


class LLMConcurrencyLimitError(LLMUpstreamError):
    code = "LLM_CONCURRENCY_LIMIT"
    public_message = "LLM request capacity is full"
    http_status = 429
    retryable = True


class LLMUpstreamConnectionError(LLMUpstreamError):
    code = "LLM_UPSTREAM_CONNECTION_ERROR"
    public_message = "LLM upstream is unavailable"
    http_status = 503
    retryable = True


class LLMGenerationTimeoutError(LLMUpstreamError):
    code = "LLM_GENERATION_TIMEOUT"
    public_message = "LLM generation timed out"
    http_status = 504
    retryable = False


class LLMRequestTimeoutError(LLMUpstreamError):
    code = "LLM_REQUEST_TIMEOUT"
    public_message = "LLM upstream request timed out"
    http_status = 504
    retryable = True


class LLMStreamProtocolError(LLMUpstreamError):
    """Raised when an upstream stream event cannot be parsed safely."""
