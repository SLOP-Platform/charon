# Ticket: rename provider config key `base` -> `base_url`

The provider config key `base` is ambiguous; rename it to `base_url`
consistently. This touches **four** independent places and all of them must be
updated for the config to load and validate — a partial rename leaves the
loader broken:

1. the config data in `config/providers.json`
2. the loader in `gateway/config_load.py` (reads the key)
3. the validator in `gateway/validate.py` (requires the key)
4. the documented example in `docs/config.md`

Update every occurrence to `base_url`. Do not leave any spot on the old name.
