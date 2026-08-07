# semgrep-money-known-good.py — FIXTURE. NOT product code, never imported, never packaged.
# The CORRECTED counterparts of every specimen in semgrep-money-known-bad.py. This is the
# baseline-silence control for the 7 money-path rules: a rule that fires on a corrected
# specimen is pattern-matching, not an invariant. The canary asserts ZERO findings here.
#
# This directory is excluded from the wrappers' tree/diff scans; the canary scans it by
# EXPLICIT path.


# --- cg-bill-on-failed-leg: usage folded ONLY on a leg that served ------------------
def bill_on_success_countusage(meter, obs, call):
    result = call()
    meter.record(obs, count_usage=True, provider="p")
    return result


def bill_on_success_ledger(cost_ledger, req_id, provider, floor):
    result = provider.send(req_id)
    cost_ledger.record(req_id, provider.name, floor, 0)
    return result


# --- cg-silent-zero-metering: absent usage raises, never bills free -----------------
def raise_cost_when_usage_absent(usage, price):
    tokens = usage.get("total_tokens")
    if tokens is None:
        raise ValueError("missing usage: unknown cost, not free")
    return price * tokens


# --- cg-conditional-debit-overdraft: unaffordable request is refused, not served -----
def debit_without_overdraft(balances, name, cost):
    remaining = balances.get(name, 0.0)
    if remaining < cost:
        raise ValueError("insufficient balance")
    balances[name] = remaining - cost
    return True


# --- cg-swallowed-spend-write: a failed debit re-raises, never silently drops --------
def raised_debit(balance_tracker, provider, cost):
    try:
        balance_tracker.record_spend(provider, cost)
    except Exception:
        raise


# --- cg-cost-zero-on-exception: pricing failure raises, never bills free ------------
def raise_cost_usd(usage, pricing):
    try:
        return usage.tokens_in * pricing["in"] + usage.tokens_out * pricing["out"]
    except KeyError:
        raise


# --- cg-unlocked-money-accumulator: the shared meter is folded under a lock ---------
class LockedMeter:
    def __init__(self, lock):
        self._lock = lock
        self._model_spend = {}

    def fold(self, key, usd):
        with self._lock:
            self._model_spend[key] = self._model_spend.get(key, 0.0) + usd


# --- cg-spend-gate-result-discarded: the verdict is acted on, not dropped -----------
def gate_honored(spend_limiter, est_cost, forward):
    if not spend_limiter.check(est_cost):
        raise ValueError("spend limit exceeded")
    return forward()
