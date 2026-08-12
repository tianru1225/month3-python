from collections.abc import Iterable


class ProviderError(RuntimeError):
    code: str = "PROVIDER_ERROR"
    public_message: str = "Model provider request failed"
    retryable: bool = False

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message)
        self.provider = provider


class ProviderCapabilityError(ProviderError):
    code = "PROVIDER_CAPABILITY_UNSUPPORTED"
    public_message = "Model provider does not support the requested capability"

    def __init__(self, *, provider: str, missing_capabilities: Iterable[str]) -> None:
        missing = tuple(sorted(set(missing_capabilities)))
        self.missing_capabilities = missing
        names = ",".join(missing)
        super().__init__(
            f"provider not support capabilities:{names}", provider=provider
        )


class ProviderExecutionError(ProviderError):
    code = "PROVIDER_EXECUTION_FAILED"

    def __init__(self, *, provider: str) -> None:
        super().__init__("model provider request failed", provider=provider)


class ProviderContractError(ProviderError):
    code = "PROVIDER_CONTRACT_INVALID"

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider)
