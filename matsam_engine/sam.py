"""SAM2 model load + inference.

The expensive stage. A loaded SamRunner is reused across screening re-tunes;
only run() (SAM inference) is costly.
"""
from __future__ import annotations

import numpy as np

from .config import Config
from .loader import rgb_for_sam


def _pick_mask(cfg: Config, cand_masks, cand_scores):
    """From (K, H, W) multimask candidates for one point, pick ONE per cfg.mask_pick.
    K is 3 when multimask=True, 1 when False."""
    if cand_masks.shape[0] == 1:
        return cand_masks[0], float(cand_scores[0])
    if cfg.mask_pick == "largest":
        k = 0
    elif cfg.mask_pick == "smallest":
        areas = cand_masks.reshape(cand_masks.shape[0], -1).sum(1)
        k = int(np.argmin(areas))
    elif cfg.mask_pick == "best":
        k = int(np.argmax(cand_scores))
    else:
        raise ValueError(f"mask_pick must be largest|smallest|best, got {cfg.mask_pick}")
    return cand_masks[k], float(cand_scores[k])


class SamRunner:
    """Loads SAM2 once; run() does inference on a seed set."""

    def __init__(self, cfg: Config, log=print):
        import torch
        from transformers import Sam2Model, Sam2Processor
        from .paths import ensure_sam2, sam2_present
        self.cfg = cfg
        self.torch = torch
        self.device = f"cuda:{cfg.gpu_index}" if torch.cuda.is_available() else "cpu"
        log(f"device: {self.device}")
        # Prefer an explicit cfg.sam2_dir if the user set one AND it has a model;
        # otherwise fall back to the app-local models/sam2, downloading on first
        # run if it isn't there yet.
        model_path = cfg.sam2_dir if (cfg.model_dir and sam2_present(cfg.sam2_dir)) else ensure_sam2(log)
        self.model = Sam2Model.from_pretrained(model_path).to(self.device)
        self.processor = Sam2Processor.from_pretrained(model_path)
        log("SAM2 loaded.")

    def run(self, S, log=print, progress=None):
        cfg = self.cfg; torch = self.torch
        img = rgb_for_sam(S["img"]); pts = S["pts"]
        masks, scores = [], []
        nb = (len(pts) + cfg.batch_size - 1) // cfg.batch_size
        for b in range(nb):
            batch = pts[b * cfg.batch_size:(b + 1) * cfg.batch_size]
            inputs = self.processor(
                images=img,
                input_points=[[[[p[0], p[1]]] for p in batch]],
                input_labels=[[[1] for _ in batch]],
                return_tensors="pt",
            ).to(self.device)
            with torch.no_grad():
                out = self.model(**inputs, multimask_output=cfg.multimask)
            m = self.processor.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"])[0]
            s = out.iou_scores.cpu()  # (1, n_pts, K)
            for i in range(m.shape[0]):
                mk, sc = _pick_mask(cfg, m[i].numpy(), s[0, i].numpy())
                masks.append(mk.astype(bool)); scores.append(sc)
            if progress is not None:
                progress(int(100 * (b + 1) / nb))
            if (b + 1) % 10 == 0 or b == nb - 1:
                log(f"  [{S['task']}] batch {b+1}/{nb}")
        if scores:
            log(f"  [{S['task']}] masks: {len(masks)} | score "
                f"[{min(scores):.3f},{max(scores):.3f}] | pick={cfg.mask_pick}")
        else:
            log(f"  [{S['task']}] WARNING: 0 masks (no seeds?).")
        return {"masks": masks, "scores": scores}
