from collections.abc import Iterable


class ProviderError(RuntimeError):
    code: str = "PROVIDER_ERROR"
    public_message: str = "Model provider request failed"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds


class ProviderCapabilityError(ProviderError):
    code = "PROVIDER_CAPABILITY_UNSUPPORTED"
    public_message = "Model provider does not support the requested capability"

    def __init__(
        self,
        *,
        provider: str,
        missing_capabilities: Iterable[str],
    ):
        missing = tuple(sorted(set(missing_capabilities)))
        self.missing_capabilities = missing
        name = ",".join(missing)
        super().__init__(
            f"provider not support capabilities:{name}",
            provider=provider,
        )


class ProviderAuthenticationError(ProviderError):
    code = "PROVIDER_AUTHENTICATION_FAILED"
    public_message = "Model provider authentication failed"

    def __init__(
        self,
        *,
        provider: str,
    ) -> None:
        super().__init__(
            "model provider authentication failed",
            provider=provider,
        )


class ProviderRateLimitError(ProviderError):
    code = "PROVIDER_RATE_LIMITED"
    public_message = "Model provider rate limit exceeded"
    retryable = True

    def __init__(
        self,
        *,
        provider: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            "model provider rate limit exceeded",
            provider=provider,
            retry_after_seconds=retry_after_seconds,
        )


class ProviderTimeoutError(ProviderError):
    code = "PROVIDER_TIMEOUT"
    public_message = "Model provider request timed out"
    retryable = True

    def __init__(
        self,
        *,
        provider: str,
    ) -> None:
        super().__init__(
            "model provider request timed out",
            provider=provider,
        )


class ProviderGenerationTimeoutError(ProviderError):
    code = "PROVIDER_GENERATION_TIMEOUT"
    public_message = "Model provider generation timed out"

    def __init__(self, *, provider: str) -> None:
        super().__init__("model provider generation timed out", provider=provider)


class ProviderUnavailableError(ProviderError):
    code = "PROVIDER_UNAVAILABLE"
    public_message = "Model provider is unavailable"
    retryable = True

    def __init__(
        self,
        *,
        provider: str,
    ) -> None:
        super().__init__(
            "model provider is unavailable",
            provider=provider,
        )


class ProviderExecutionError(ProviderError):
    code = "PROVIDER_EXECUTION_FAILED"

    def __init__(
        self,
        *,
        provider: str,
    ) -> None:
        super().__init__(
            "model provider request failed",
            provider=provider,
        )


class ProviderContractError(ProviderError):
    code = "PROVIDER_CONTRACT_INVALID"

    def __init__(
        self,
        message: str,
        *,
        provider: str,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
        )
