#!/usr/bin/env bash
set -uo pipefail

ROOT="${RATCHET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BASE="${RATCHET_BASE:-${RIG_CI_BASE:-origin/master}}"
HEAD_REF="${RATCHET_HEAD:-${RIG_CI_HEAD:-HEAD}}"

red=0
red(){ echo "RED: $*"; red=1; }

base_sha="$(git -C "$ROOT" rev-parse --verify -q "${BASE}^{commit}" 2>/dev/null || true)"
head_sha="$(git -C "$ROOT" rev-parse --verify -q "${HEAD_REF}^{commit}" 2>/dev/null || true)"
if [ -z "$base_sha" ] || [ -z "$head_sha" ]; then
  echo "RED: board-file-ratchet cannot resolve BASE '$BASE' or HEAD '$HEAD_REF'" >&2
  exit 1
fi

mapfile -t before < <(git -C "$ROOT" ls-tree -r --name-only "$base_sha" -- fleet/board/ | while IFS= read -r p; do case "$p" in fleet/board/*.md) basename "$p";; esac; done | sort)
mapfile -t after < <(git -C "$ROOT" ls-tree -r --name-only "$head_sha" -- fleet/board/ | while IFS= read -r p; do case "$p" in fleet/board/*.md) basename "$p";; esac; done | sort)
mapfile -t archived < <(git -C "$ROOT" ls-tree -r --name-only "$head_sha" -- fleet/board/archive/ | while IFS= read -r p; do case "$p" in fleet/board/archive/*.md) basename "$p";; esac; done | sort)
mapfile -t changed_archive < <(git -C "$ROOT" diff --name-only "$base_sha" "$head_sha" -- fleet/board/archive/ | while IFS= read -r p; do case "$p" in fleet/board/archive/*.md) basename "$p";; esac; done | sort)

messages="$(git -C "$ROOT" log --format=%B "$base_sha..$head_sha" 2>/dev/null || true)"
for ticket in "${before[@]}"; do
  [ -n "$ticket" ] || continue
  if ! printf '%s\n' "${after[@]}" | grep -Fqx "$ticket"; then
    if printf '%s\n' "${archived[@]}" | grep -Fqx "$ticket" && printf '%s\n' "${changed_archive[@]}" | grep -Fqx "$ticket"; then
      continue
    fi
    id="${ticket%.md}"
    if grep -Eiq "board-hygiene:[[:space:]]*retire[[:space:]]+$id([[:space:]]|$)" <<<"$messages"; then
      continue
    fi
    red "$ticket disappeared from fleet/board/ without archive move or declared retire"
  fi
done

if [ "$red" -eq 0 ]; then
  echo "board-file-ratchet: GREEN (base board tickets are retained or explicitly retired)"
fi
exit "$red"
