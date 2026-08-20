# Phoenix HTTP Authentication

All Phoenix-controlled HTTP services use one request format for protected routes:

```http
Authorization: Bearer <PHOENIX_AUTH>
```

Clients read the token from `PHOENIX_AUTH`; services compare it to their deployed
secret of the same name. Do not send authentication tokens in query parameters,
custom `X-Phoenix-Auth` headers, logs, or browser-visible configuration.

`PHOENIX_AUTH` is currently a shared service token. It is suitable for a trusted
self-hosted deployment, but it is not per-user identity or authorization. Keep
distinct credentials for third-party providers (for example `ANTHROPIC_API_KEY`)
and for future role-specific services.

Local Electron IPC and loopback-only utilities are not HTTP services; they rely on
the signed local application boundary and must not expose their privileged actions
to remote content.
