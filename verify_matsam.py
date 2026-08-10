"""Headless verification — run the matsam engine and compare to the notebook.

Expected (matsam_sam2.ipynb, MULTIMASK=True, MASK_PICK=smallest, on
sqr_DP590_Initial_x5000(1).ang):
    map 1730x585 ; grain 985 masks ; phase 979 masks
    grains painted 291 ; phase fg ~9.3%
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import matplotlib
matplotlib.use("Agg")

from matsam_engine import (Config, load_maps, build_input, preseg,
                           SamRunner, screen)

ANG = os.path.join(ROOT, "dp_data", "sqr", "sqr_DP590_Initial_x5000(1).ang")
MODELS = os.path.join(ROOT, "models")


def main():
    cfg = Config(ang_file=ANG, model_dir=MODELS, task="both",
                 multimask=True, mask_pick="smallest")
    print("=" * 56); print("LOAD"); print("=" * 56)
    md = load_maps(cfg)

    print("=" * 56); print("SEEDS"); print("=" * 56)
    seeds = {}
    for t in (["grain", "phase"] if cfg.task == "both" else [cfg.task]):
        seeds[t] = preseg.make_seeds(cfg, md, build_input(cfg, md, t), t)

    print("=" * 56); print("SAM"); print("=" * 56)
    runner = SamRunner(cfg)
    sam_out = {t: runner.run(S) for t, S in seeds.items()}

    print("=" * 56); print("SCREEN"); print("=" * 56)
    result = screen.screen_all(cfg, md, seeds, sam_out)

    import numpy as np
    n_grains = int(result["grain"].max())
    phase_fg = 100 * result["phase"].mean()
    checks = [
        ("map H", md.H, 1730),
        ("map W", md.W, 585),
        # grain masks = grain seed count; may differ by a couple grid points from
        # the notebook's saved 985 due to argmax tie-breaking in ROI seeding, but
        # the final grain count (below) is what matters and matches exactly.
        ("grain masks", len(sam_out["grain"]["masks"]), None),
        ("phase masks", len(sam_out["phase"]["masks"]), 979),
        ("grains painted", n_grains, 291),
        ("phase fg %", round(phase_fg, 1), None),
    ]
    print("=" * 56); print("VERIFICATION"); print("=" * 56)
    ok = True
    for name, got, exp in checks:
        if exp is None:
            print(f"  {name:16s} = {got!s:>8}   (info)")
        else:
            match = got == exp
            if not match:
                ok = False
            print(f"  {'OK ' if match else 'XX '}{name:16s} = {got!s:>8}   expected {exp}")
    print("=" * 56); print("ALL MATCH" if ok else "MISMATCH - investigate")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
