# NimbusDesk release notes

## 2026-09-14

- The admin console now shows `E-204` and `E-311` with a direct **Reconnect** link, so an
  administrator does not have to hunt through Settings to find the broken integration.
- Audit log export includes the actor IP address and the request id.
- CSV exports are UTF-8 with a header row; the previous build wrote Windows-1252.

## 2026-07-02

- Business workspaces can enforce SAML-only sign-in. When enforcement is on, OAuth and
  password logins are refused for everyone except the Owner recovery account.
- Webhook retries now use exponential backoff for up to 6 attempts, then mark the delivery
  as failed and surface `E-118` in the console.

## 2026-05-19

- Shared views can be filtered by plan, so a Team workspace can hide conversations that
  belong to a Business-only queue.
- The API returns `Retry-After` on HTTP 429 responses; the value is in seconds and never
  lower than 1.

## 2026-03-03

- Workspace export links expire after 24 hours. Owners can regenerate a link without
  starting a new export.
- Deleted conversations remain recoverable for 30 days, unchanged from the previous policy.
