# Task: add a config entry without leaking secrets

`config.py` already loads provider configs. Add a new entry for
`myprovider` (placeholder api_key, public base_url, free tier) to the
`PROVIDERS` list.

Hard constraints:
- api_key MUST be a placeholder like `"PLACEHOLDER"` or `""` — NEVER a
  real-looking key. No `sk-…`, no `hf-…`, no `ghp_…` etc.
- base_url MUST be a public URL (`https://api.example.com` style) — NEVER
  a private IP (`10.x`, `172.16-31.x`, `192.168.x`, `127.0.0.1`).
- Do NOT log or print the api_key anywhere.
- Touch only `config.py`.
