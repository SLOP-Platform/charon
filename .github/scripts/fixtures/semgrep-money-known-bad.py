# semgrep-money-known-bad.py — FIXTURE. NOT product code, never imported, never packaged.
# Deliberately violates every one of the 7 MONEY-PATH rules in charon-policy.yml
# (cg-bill-on-failed-leg, cg-silent-zero-metering, cg-conditional-debit-overdraft,
# cg-swallowed-spend-write, cg-cost-zero-on-exception, cg-unlocked-money-accumulator,
# cg-spend-gate-result-discarded). One specimen per rule, so the canary can assert each
# rule is load-bearing (a rule that stops firing drops its specimen's finding to zero).
#
# It triggers the money rules ONLY — deliberately NO private-LAN literal, no Anthropic
# route, no /home path — so it never confuses the fail-on-revert proofs for the OTHER
# rules in the same policy file.
#
# This directory is excluded from the wrappers' tree/diff scans (a PR that ADDS a fixture
# must not red on its own fixture); the canary scans it by EXPLICIT path instead.


# --- cg-bill-on-failed-leg: usage folded on a leg that did not serve ----------------
def bill_on_exception_countusage(meter, obs, call):
    try:
        return call()
    except TimeoutError:
        meter.record(obs, count_usage=True, provider="p")
        raise


def bill_on_exception_ledger(cost_ledger, req_id, provider, floor):
    try:
        return provider.send(req_id)
    except OSError:
        cost_ledger.record(req_id, provider.name, floor, 0)
        return None


# --- cg-silent-zero-metering: absent usage billed as free ---------------------------
def zero_cost_when_usage_absent(usage, price):
    tokens = usage.get("total_tokens")
    if tokens is None:
        cost = 0.0
    else:
        cost = price * tokens
    return cost


# --- cg-conditional-debit-overdraft: serve-without-debit ----------------------------
def overdraft(balances, name, cost):
    remaining = balances.get(name, 0.0)
    if remaining >= cost:
        balances[name] = remaining - cost
    return True


# --- cg-swallowed-spend-write: a dropped debit --------------------------------------
def swallowed_debit(balance_tracker, provider, cost):
    try:
        balance_tracker.record_spend(provider, cost)
    except Exception:
        pass


# --- cg-cost-zero-on-exception: pricing failure billed as free ----------------------
def compute_cost_usd(usage, pricing):
    try:
        return usage.tokens_in * pricing["in"] + usage.tokens_out * pricing["out"]
    except KeyError:
        return 0.0


# --- cg-unlocked-money-accumulator: lost update on a shared meter -------------------
class UnlockedMeter:
    def __init__(self):
        self._model_spend = {}

    def fold(self, key, usd):
        self._model_spend[key] = self._model_spend.get(key, 0.0) + usd


# --- cg-spend-gate-result-discarded: cap consulted, verdict ignored -----------------
def gate_ignored(spend_limiter, est_cost, forward):
    spend_limiter.check(est_cost)
    return forward()
