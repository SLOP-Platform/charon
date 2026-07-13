# Ticket: regression test for auth-header redaction

`gateway/headers.py::redact_auth(headers)` strips credential headers before we
log a request, so tokens never reach the logs. It works today, but it has no
test — a future refactor could silently break it and we would leak credentials.

Add a regression test (in `tests/`) that pins the behavior of `redact_auth`:
it must prove that the `Authorization` header (and any `x-api-key`) is removed
while ordinary headers are preserved. The test should fail if `redact_auth`
ever stops redacting.
