# Qwen Provider Contracts

## Scope

Qwen is the only cloud model provider in the current stage. Application code depends on the vendor-neutral `ModelProvider`, `ModelRequest`, `ModelResult`, `ModelUsage`, and stream-event contracts. Qwen-specific HTTP payloads and error codes stay inside `QwenAdapter`.

The implementation was reviewed against the Alibaba Cloud Model Studio error-code page on 2026-08-20:

- https://help.aliyun.com/zh/model-studio/error-code
- Page title: 错误码 - 大模型服务平台百炼（Model Studio）
- Page last modified: 2026-08-18

The configured compatible-mode endpoint is `https://dashscope.aliyuncs.com/compatible-mode/v1`. The model is selected by `QWEN_MODEL`; the Stage 4 deployment uses `qwen3.8-max`.

## Capabilities

The Qwen adapter declares these capabilities:

- chat completion;
- streaming completion;
- structured output through JSON Schema;
- token usage.

Unsupported capabilities are rejected before an upstream request is sent. Vendor exceptions and response shapes do not cross the Provider boundary.

## Request contract

For ordinary non-structured requests, `ModelRequest.max_output_tokens` is translated to the compatible API field `max_completion_tokens`. The deprecated `max_tokens` field is not sent.

For structured-output requests, the adapter sends `response_format.type=json_schema` with strict schema validation. It sends neither `max_tokens` nor `max_completion_tokens`, because the currently documented Qwen structured-output path rejects output-limit parameters in this combination.

Streaming requests set `stream=true` and `stream_options.include_usage=true`. A valid application stream emits zero or more `text_delta` events, an optional `usage` event when Qwen reports usage, and one terminal `done` event. An upstream protocol failure is converted to the application error boundary and does not expose the raw event.

## HTTP and retry matrix

| Upstream condition | Provider error | Retryable | Retry-After |
|---|---|---:|---|
| 401 or 403 | `ProviderAuthenticationError` | No | Ignored |
| Retryable 429 code | `ProviderRateLimitError` | Yes | Parsed when present |
| Non-retryable/unknown 429 code | `ProviderRateLimitError` | No | Ignored |
| Other 4xx, including content-policy 400 | `ProviderExecutionError` | No | Ignored |
| Connect/write/pool timeout | `ProviderTimeoutError` | Yes | Not applicable |
| Read/generation timeout | `ProviderGenerationTimeoutError` | No | Not applicable |
| Connection failure or 5xx | `ProviderUnavailableError` | Yes | Not applicable |
| Invalid success payload or stream event | Safe contract failure | No | Not applicable |

The execution layer owns retries. The adapter makes one HTTP attempt per call. Retryable failures use bounded attempts and backoff. A stream may retry only before its first event; after any event is emitted, it must not retry because replay could duplicate user-visible output.

`Retry-After` is optional. It is inspected only after a 429 code has been classified as retryable. Both delta-seconds and HTTP-date forms are accepted. Missing or invalid values fall back to bounded local backoff. A delay above the configured maximum stops retrying.

## Qwen 429 classification

Retryable frequency, burst, or concurrency codes:

```text
Throttling
Throttling.RateQuota
LimitRequests
limit_requests
ResourceExhausted
Too many requests
Throttling.BurstRate
limit_burst_rate
Throttling.Concurrency
```

Non-retryable purchase, billing, or fixed-allocation codes:

```text
Throttling.AllocationQuota
insufficient_quota
CommodityNotPurchased
PrepaidBillOverdue
PostpaidBillOverdue
```

`Throttling.AllocationQuota` is treated conservatively as non-retryable because its documented resolution requires allocation or strategy changes rather than immediate replay. Missing, blank, non-string, invalid-JSON, and unknown codes are also non-retryable.

## Secret and logging boundary

`DASHSCOPE_API_KEY` is loaded as `SecretStr`. Only `QwenAdapter` reads its plaintext value to build the upstream Authorization header. Logs and exceptions may contain the Provider name, safe application error code, retryability, attempt count, delay, latency, request ID, model name, and token counts.

They must not contain API keys, Authorization headers, `.env`, database URLs, prompts, model output, or raw Provider response bodies. Authentication errors and malformed upstream responses are converted to stable public errors.

## Stage 4 verification

- Mock non-streaming contract: passed.
- Mock streaming and cancellation contract: passed.
- Structured-output request contract: passed.
- Retryable/non-retryable/unknown 429 matrix: passed.
- Retry ownership and bounded-attempt contract: passed.
- Real minimal non-streaming smoke: [填写 passed，或 skipped 及明确原因].
- Real minimal streaming smoke: [填写 passed，或 skipped 及明确原因].

No API key, prompt, model answer, Authorization header, or raw Provider response is retained in this document.