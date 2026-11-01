#!/usr/bin/env python3
"""One-command publisher to mount the 9-row BioSniper benchmark sample onto HuggingFace Datasets
and wire automatic daily sync into GitHub Actions (`josephzbio/biotech-catalyst-benchmark`).

Usage:
    HF_TOKEN=hf_xxx python3 docs/growth/open-source-kit/publish_to_huggingface.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
UPLOAD_FILES: tuple[str, ...] = (
    "README.md",
    "CATALOG.md",
    "CITATION.cff",
    "biosniper_toolkit.py",
    "data/biotech_catalysts_runway.csv",
    "data/biotech_catalysts_runway.json",
    "data/WEEKLY_DIGEST.md",
    "data/CITATIONS_AND_QA_PACK.md",
)


def resolve_hf_token(explicit_token: str | None = None) -> str | None:
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()
    env_tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if env_tok and env_tok.strip():
        return env_tok.strip()
    token_file = Path.home() / ".cache" / "huggingface" / "token"
    if token_file.exists():
        content = token_file.read_text(encoding="utf-8").strip()
        if content:
            return content
    return None


def publish_dataset_to_hf(
    token: str,
    repo_name: str = "biotech-catalyst-benchmark",
    gh_repo: str = "josephzbio/biotech-catalyst-benchmark",
) -> str:
    from huggingface_hub import HfApi  # type: ignore[import-not-found]

    api = HfApi(token=token)
    user_info = api.whoami()
    username = user_info.get("name")
    if not username:
        raise RuntimeError("Could not determine HuggingFace username from token.")

    repo_id = f"{username}/{repo_name}" if "/" not in repo_name else repo_name
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=True)

    for rel_path in UPLOAD_FILES:
        local_path = KIT_DIR / rel_path
        if not local_path.exists():
            continue
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=rel_path,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Sync {rel_path} (BioSniper 9-row public benchmark sample)",
        )

    # Wire HF_TOKEN & HF_DATASET_REPO into GitHub Actions for automatic daily sync
    try:
        gh_tok = subprocess.check_output(
            ["gh", "auth", "token", "--user", "josephzbio"], text=True
        ).strip()
        env = {**os.environ, "GH_TOKEN": gh_tok}
        subprocess.run(
            ["gh", "secret", "set", "HF_TOKEN", "--repo", gh_repo, "--body", token],
            env=env,
            check=True,
        )
        subprocess.run(
            ["gh", "variable", "set", "HF_DATASET_REPO", "--repo", gh_repo, "--body", repo_id],
            env=env,
            check=True,
        )
    except Exception as exc:
        print(f"[warn] Uploaded to HF, but could not auto-set GitHub Actions secret/variable: {exc}", file=sys.stderr)

    return f"https://huggingface.co/datasets/{repo_id}"


def main() -> int:
    token = resolve_hf_token()
    if not token:
        print(
            "Error: No HuggingFace token found.\n"
            "Please provide a write token via:\n"
            "  HF_TOKEN=hf_xxx backend/venv/bin/python docs/growth/open-source-kit/publish_to_huggingface.py",
            file=sys.stderr,
        )
        return 1
    url = publish_dataset_to_hf(token)
    print(f"Successfully published HuggingFace dataset and wired daily GitHub sync: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
