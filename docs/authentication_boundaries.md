# Authentication Boundaries

## Two credentials

Bearer JWT identifies an authenticated product user. x-api-key identifies a service caller allowed to use the current gateway.

| Credential | Endpoints |
|---|---|
| Authorization: Bearer JWT | /users/me, /users/{user_id} |
| x-api-key | /items, /v1/chat, /v1/chat/stream |

They are independent and cannot replace each other.

## JWT rules

The token uses HS256 and contains sub, iat and exp. The subject is a positive user ID string. The default lifetime is 30 minutes. JWT_SECRET_KEY is a SecretStr and must contain at least 32 characters.

This stage has no refresh token, roles, revocation list or OAuth. The current-user dependency reloads the user for every request and rejects a user that is no longer ACTIVE.

Unknown usernames and wrong passwords both return 401 INVALID_CREDENTIALS. DISABLED and LOCKED users return 403 USER_NOT_ACTIVE after a correct password.

Logs may contain method, path, status, request ID and elapsed time. They must not contain passwords, hashes, JWTs, Authorization headers, API keys or secrets. Rotating JWT_SECRET_KEY invalidates existing access tokens.