#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python - <<'PY'
import json
from pathlib import Path

root = Path.cwd()
json_files = list(root.rglob("*.json"))
for path in json_files:
    json.loads(path.read_text(encoding="utf-8"))

gate = json.loads((root / "results/gate3/gate_decision.json").read_text())
mastitis = json.loads((root / "results/mastitis/full/gate_decision.json").read_text())
hiv = json.loads((root / "results/hemophilia_hiv/full/gate_decision.json").read_text())
assert gate["decision"] == "ADVANCE_BOTH"
assert mastitis["decision"] == "NEUTRAL"
assert hiv["decision"] == "NEUTRAL"
assert (root / "results/mastitis/full/RUN_COMPLETE").is_file()
assert (root / "results/hemophilia_hiv/full/RUN_COMPLETE").is_file()
assert len(list((root / "results/mastitis/full/replicates").glob("replicate_*.json"))) == 500
assert len(list((root / "results/hemophilia_hiv/full/replicates").glob("replicate_*.json"))) == 500
print(f"Validated {len(json_files)} JSON files and all frozen decisions/completion counts.")
PY

printf '%s\n' 'Testing study/gate3_base'
(cd study/gate3_base && PYTHONPATH=src python -m pytest -q tests)

printf '%s\n' 'Testing study/gate3_hotfix (offline-safe subset)'
(cd study/gate3_hotfix && PYTHONPATH=src python -m pytest -q tests \
  -k 'not test_gbsg2_reference_encoding_is_full_rank')

for component in study/external_mastitis study/external_hemophilia_hiv; do
  printf 'Testing %s\n' "$component"
  (cd "$component" && PYTHONPATH=src python -m pytest -q tests)
done

if [[ -f MANIFEST.sha256 ]]; then
  sha256sum --check MANIFEST.sha256 >/dev/null
  printf '%s\n' 'Manifest hashes passed.'
fi

printf '%s\n' 'Repository verification passed.'
