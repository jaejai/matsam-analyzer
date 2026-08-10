"""Where the app keeps its SAM2 model, and how it gets there.

The model lives in a FIXED, app-relative folder: ``<app>/models/sam2``. The app
always looks there first. If it's missing (the common case for a fresh user),
``ensure_sam2`` downloads ``facebook/sam2-hiera-large`` (Apache-2.0, ungated)
into exactly that folder, then the app uses it. If the download can't happen
(offline / corporate SSL proxy), it raises with a clear message so the user can
drop the files in manually.
"""
from __future__ import annotations

import os

# The app root = the standalone_matsam folder (this file is matsam_engine/paths.py).
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# HuggingFace repo id for the ungated, Apache-2.0 SAM2 large model.
SAM2_REPO = "facebook/sam2-hiera-large"

# Only these files are needed to load via transformers (safetensors weights +
# configs). We deliberately do NOT fetch sam2_hiera_large.pt (a pickle) — the
# safetensors path has no code-execution risk.
SAM2_ALLOW = [
    "config.json",
    "model.safetensors",
    "preprocessor_config.json",
    "processor_config.json",
    "*.yaml",
]


def models_dir() -> str:
    """The models directory the app uses.

    Order of preference:
      1. ``$MATSAM_MODELS_DIR`` if set (explicit override).
      2. The in-repo dev location ``<repo>/models`` if it already holds a SAM2
         model (so existing checkouts keep working without a re-download).
      3. The app-local ``<app>/models`` (the packaged/default location).
    """
    override = os.environ.get("MATSAM_MODELS_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override

    repo_models = os.path.join(os.path.dirname(APP_ROOT), "models")
    if os.path.isfile(os.path.join(repo_models, "sam2", "model.safetensors")):
        return repo_models

    d = os.path.join(APP_ROOT, "models")
    os.makedirs(d, exist_ok=True)
    return d


def sam2_dir() -> str:
    """SAM2 folder inside the resolved models directory (``.../models/sam2``)."""
    return os.path.join(models_dir(), "sam2")


def sam2_present(path: str | None = None) -> bool:
    """True if a usable SAM2 model (safetensors + config) is already on disk."""
    path = path or sam2_dir()
    return (os.path.isfile(os.path.join(path, "config.json"))
            and os.path.isfile(os.path.join(path, "model.safetensors")))


def ensure_sam2(log=print) -> str:
    """Return the local SAM2 folder, downloading it on first run if needed.

    1. If ``models/sam2`` already has the model -> return it (no network).
    2. Else download from HuggingFace into that folder.
    3. If the download fails -> raise RuntimeError with a manual-install hint.
    """
    dst = sam2_dir()
    if sam2_present(dst):
        log(f"SAM2 found: {dst}")
        return dst

    log(f"SAM2 not found locally; downloading {SAM2_REPO} (~0.9 GB, first run only)...")
    os.makedirs(dst, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=SAM2_REPO,
            local_dir=dst,
            allow_patterns=SAM2_ALLOW,
        )
    except Exception as e:  # network down, SSL proxy, HF outage, ...
        raise RuntimeError(
            "Could not download the SAM2 model automatically.\n\n"
            f"Reason: {e}\n\n"
            "This is usually a network issue or a corporate proxy/firewall "
            "blocking huggingface.co.\n"
            "Fix the connection and relaunch, OR manually place the model files "
            f"({', '.join(SAM2_ALLOW)}) from\n"
            f"    https://huggingface.co/{SAM2_REPO}\n"
            f"into:\n    {dst}"
        ) from e

    if not sam2_present(dst):
        raise RuntimeError(
            f"SAM2 download finished but files are missing in {dst}. "
            "Please retry or install the model manually."
        )
    log(f"SAM2 downloaded to {dst}")
    return dst
