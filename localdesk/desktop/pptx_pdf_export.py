"""Isolated LibreOffice PPTX-to-PDF conversion helper.

Keeping this in a fresh Python process avoids inheriting presentation-generation
runtime state that can make soffice unstable on Windows.
"""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path


def export(soffice: Path, pptx: Path, output_dir: Path, profile: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{pptx.stem}.pdf"
    last_detail = "unknown error"
    last_code = -1
    for attempt in range(1, 4):
        attempt_profile = profile.with_name(f"{profile.name}-{attempt}")
        attempt_profile.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                str(soffice),
                "--headless",
                f"-env:UserInstallation={attempt_profile.resolve().as_uri()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(pptx),
            ],
            capture_output=True,
            timeout=120,
        )
        last_code = result.returncode
        last_detail = (result.stderr or result.stdout or b"unknown error")[-600:].decode("utf-8", errors="replace")
        for _ in range(20):
            if target.is_file() and target.stat().st_size:
                return target
            time.sleep(0.25)
        time.sleep(2)
    raise RuntimeError(f"LibreOffice exit={last_code}: {last_detail}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--soffice", type=Path, required=True)
    parser.add_argument("--pptx", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    print(export(args.soffice, args.pptx, args.output_dir, args.profile))
