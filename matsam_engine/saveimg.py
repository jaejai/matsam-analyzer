"""Save result figures as image files."""
from __future__ import annotations

import os

from .config import Config


def save_figure(fig, outfile: str, cfg: Config, log=print) -> str:
    """Save one matplotlib Figure to outfile (format inferred from extension or
    cfg.save_format). Returns the path written."""
    fmt = os.path.splitext(outfile)[1].lstrip(".").lower() or cfg.save_format.lower()
    # Bare single-image figures carry a marker so they save with NO padding at
    # all (just the pixels). Everything else gets the usual tight bbox.
    if getattr(fig, "_bare_image", False):
        fig.savefig(outfile, dpi=cfg.fig_dpi, format=fmt,
                    bbox_inches="tight", pad_inches=0)
    else:
        fig.savefig(outfile, dpi=cfg.fig_dpi, format=fmt, bbox_inches="tight")
    log(f"Saved {outfile} ({fmt.upper()}, {cfg.fig_dpi} dpi)")
    return outfile


def save_figures(figs: dict, outdir: str, prefix: str, cfg: Config, log=print) -> list:
    """Save several named figures as separate files: <outdir>/<prefix>_<name>.<ext>."""
    ext = cfg.save_format.lower()
    paths = []
    for name, fig in figs.items():
        p = os.path.join(outdir, f"{prefix}_{name}.{ext}")
        fig.savefig(p, dpi=cfg.fig_dpi, format=ext, bbox_inches="tight")
        paths.append(p)
    log(f"Saved {len(paths)} image(s) to {outdir}")
    return paths
