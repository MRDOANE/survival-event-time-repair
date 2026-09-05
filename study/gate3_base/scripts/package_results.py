from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir")
    parser.add_argument("target")
    args = parser.parse_args()
    output = Path(args.output_dir).resolve()
    target = Path(args.target).resolve()
    gate_path = output / "gate_decision.json"
    if not gate_path.is_file():
        raise SystemExit(f"missing decisive output: {gate_path}")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if (
        gate.get("decision") == "INCONCLUSIVE"
        and gate.get("trial_completeness", {}).get("complete") is False
    ):
        raise SystemExit("refusing to package an incomplete trial grid")
    files = [
        path
        for path in output.rglob("*")
        if path.is_file() and "work" not in path.relative_to(output).parts
    ]
    checksums = (
        "\n".join(
            f"{sha256(path)}  {path.relative_to(output)}" for path in sorted(files)
        )
        + "\n"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        root_name = output.name
        for path in sorted(files):
            archive.write(path, Path(root_name) / path.relative_to(output))
        archive.writestr(str(Path(root_name) / "RESULT_SHA256SUMS.txt"), checksums)
    print(target)
    print(f"sha256={sha256(target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
