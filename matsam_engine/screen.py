"""Mask screening — turn raw SAM masks into final grain / phase results.

Ports notebook §8. Cheap; re-run freely while tuning min_score / max_mask_frac
without re-running SAM.
"""
from __future__ import annotations

import numpy as np
from skimage.filters import threshold_otsu
from skimage.morphology import remove_small_objects

from .config import Config, per_task
from .loader import MapData
from .preseg import phase_fg


def screen_phase(cfg, md, img_u8, masks, scores, otsu_binary, min_score, min_area, max_area, log=print):
    H, W = md.H, md.W
    t = threshold_otsu(img_u8)
    fg = np.zeros((H, W), bool); kept = 0; drop_big = 0
    for m, s in zip(masks, scores):
        a = m.sum()
        if s < min_score or a < min_area:
            continue
        if a > max_area:
            drop_big += 1; continue
        if img_u8[m].mean() < t:
            fg |= (m & otsu_binary)
            kept += 1
    # skimage >=0.26 renamed the threshold to max_size (positional min_size is
    # deprecated); max_size=N is behaviourally identical to the old min_size=N.
    fg = remove_small_objects(fg, max_size=min_area)
    log(f"  [phase] kept {kept}/{len(masks)} | fg {100*fg.mean():.1f}% "
        f"(min_score={min_score}, min_area={min_area}, dropped_oversize={drop_big})")
    return fg


def screen_grain(cfg, md, masks, scores, min_score, min_area, max_area, log=print):
    H, W = md.H, md.W
    order = np.argsort(scores)[::-1]
    lab = np.zeros((H, W), int); nid = 0; drop_big = 0
    for idx in order:
        m, s = masks[idx], scores[idx]
        a = m.sum()
        if s < min_score or a < min_area:
            continue
        if a > max_area:
            drop_big += 1; continue
        free = (lab == 0) & m
        if free.sum() < min_area:
            continue
        nid += 1; lab[free] = nid
    log(f"  [grain] grains painted: {nid} "
        f"(min_score={min_score}, min_area={min_area}, dropped_oversize={drop_big})")
    # clean up the raw label map (despeckle / merge / smooth / morph / fill)
    return postprocess_grain(cfg, lab, min_area, log)


# ============================================================================
#  Grain-map post-processing — each step is an independent toggle. Applied in
#  order: despeckle/merge (remove noise objects) -> majority filter (smooth
#  edges) -> morphological cleanup (round shapes) -> fill gaps (no black bg).
# ============================================================================
def _fill_gaps(lab):
    """Assign every label-0 pixel the label of its nearest non-zero pixel
    (Euclidean nearest-neighbour), so the grain map has no black background."""
    from scipy.ndimage import distance_transform_edt
    if lab.max() == 0 or not (lab == 0).any():
        return lab
    _, (iy, ix) = distance_transform_edt(lab == 0, return_indices=True)
    return lab[iy, ix]


def _despeckle(lab, min_area):
    """Drop connected components smaller than min_area (set them to 0). Their
    pixels get reassigned later by the gap-fill (nearest grain)."""
    from skimage.measure import label as cc_label, regionprops
    cc = cc_label(lab, connectivity=1, background=0)
    out = lab.copy()
    removed = 0
    for p in regionprops(cc):
        if p.area < min_area:
            out[cc == p.label] = 0; removed += 1
    return out, removed


def _merge_fragments(lab, min_area):
    """Merge each sub-min_area connected component into the neighbouring grain
    it shares the longest border with (relabels the fragment's pixels)."""
    from skimage.measure import label as cc_label, regionprops
    from scipy.ndimage import binary_dilation
    cc = cc_label(lab, connectivity=1, background=0)
    out = lab.copy()
    merged = 0
    for p in regionprops(cc):
        if p.area >= min_area:
            continue
        comp = cc == p.label
        # 1-px ring around the fragment; the label appearing most there wins
        ring = binary_dilation(comp, iterations=1) & ~comp
        neigh = out[ring]
        neigh = neigh[(neigh != 0) & (neigh != out[comp][0])]
        if neigh.size:
            vals, counts = np.unique(neigh, return_counts=True)
            out[comp] = vals[counts.argmax()]; merged += 1
    return out, merged


def _majority_filter(lab, size):
    """Replace each pixel with the modal label in a (size x size) window —
    smooths frayed boundaries and removes salt-and-pepper speckle."""
    from scipy.ndimage import generic_filter
    size = int(size) | 1                       # force odd
    def _mode(v):
        vals, counts = np.unique(v, return_counts=True)
        return vals[counts.argmax()]
    return generic_filter(lab, _mode, size=size, mode="nearest").astype(lab.dtype)


def _morph_cleanup(lab, radius):
    """Per-label morphological opening then closing (disk radius) to round off
    protrusions and fill pinholes, without merging separate grains."""
    # skimage >=0.26 deprecated binary_opening/binary_closing; `opening`/`closing`
    # give identical bool output on a boolean image.
    from skimage.morphology import opening, closing, disk
    from scipy.ndimage import distance_transform_edt
    se = disk(int(radius))
    out = np.zeros_like(lab)
    for lb in np.unique(lab):
        if lb == 0:
            continue
        m = closing(opening(lab == lb, se), se)
        out[m] = lb
    # opening can leave new holes -> fill any label-0 by nearest grain
    if (out == 0).any() and out.max() > 0:
        _, (iy, ix) = distance_transform_edt(out == 0, return_indices=True)
        out = out[iy, ix]
    return out


def postprocess_grain(cfg, lab, min_area, log=print):
    """Apply the enabled grain-map cleanup steps (each an independent toggle)."""
    pp_area = int(getattr(cfg, "pp_min_grain_area", min_area) or min_area)
    if getattr(cfg, "pp_despeckle", False):
        lab, n = _despeckle(lab, pp_area); log(f"  [grain] despeckle: removed {n} tiny objects")
    if getattr(cfg, "pp_merge_fragments", False):
        lab, n = _merge_fragments(lab, pp_area); log(f"  [grain] merge: {n} fragments merged")
    if getattr(cfg, "pp_majority", False):
        lab = _majority_filter(lab, getattr(cfg, "pp_majority_size", 3))
        log(f"  [grain] majority filter (size {int(getattr(cfg, 'pp_majority_size', 3)) | 1})")
    if getattr(cfg, "pp_morph", False):
        lab = _morph_cleanup(lab, getattr(cfg, "pp_morph_radius", 1))
        log(f"  [grain] morphological cleanup (r={getattr(cfg, 'pp_morph_radius', 1)})")
    if getattr(cfg, "fill_grain_gaps", True) and lab.max() > 0 and (lab == 0).any():
        lab = _fill_gaps(lab); log("  [grain] filled gaps (no black background)")
    return lab


def screen_all(cfg: Config, md: MapData, seeds: dict, sam_out: dict, log=print) -> dict:
    """Run screening for every task present in seeds/sam_out. Returns {task: result}."""
    max_area = int(cfg.max_mask_frac * md.H * md.W)
    result = {}
    for t, S in seeds.items():
        o = sam_out[t]
        ms = per_task(cfg.min_score, t)
        ma = per_task(cfg.min_mask_area, t)
        if t == "phase":
            ob = phase_fg(cfg, S["img"], cfg.preseg_phase)
            result[t] = screen_phase(cfg, md, S["img"], o["masks"], o["scores"], ob, ms, ma, max_area, log)
        else:
            result[t] = screen_grain(cfg, md, o["masks"], o["scores"], ms, ma, max_area, log)
    return result
