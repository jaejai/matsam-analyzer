"""Configuration for the MatSAM (grain + phase) segmentation pipeline.

Mirrors the `## 0. Master control` cell of matsam_sam2.ipynb as a dataclass so
the GUI / CLI can drive it instead of editing module globals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

# per-task params may be a scalar (same for grain & phase) or [grain, phase]
PerTask = Union[float, int, list]


@dataclass
class Config:
    # --- master switch -------------------------------------------------------
    task: str = "both"               # "grain" | "phase" | "both"
    input_channel: str = "iq"        # "iq" | "composite" (IQ x (1-KAM));
                                     # applies to BOTH grain and phase tasks

    # --- compute -------------------------------------------------------------
    gpu_index: int = 0              # CUDA device index; CPU fallback if no GPU

    # --- paths ---------------------------------------------------------------
    model_dir: str = ""            # folder holding the SAM2 model
    ang_file: str = ""             # full path to the .ang scan

    # --- grain pre-segmentation ---------------------------------------------
    preseg_grain: str = "watershed"   # "otsu_edge" | "canny" | "watershed" | "slic"
    canny_blur: int = 3
    canny_lo: int = 50
    canny_hi: int = 150
    canny_min_size: int = 15
    canny_erode: int = 0
    canny_dilate: int = 5
    otsu_edge_blur: int = 3
    otsu_edge_offset: int = 0
    otsu_edge_min_size: int = 15
    otsu_edge_erode: int = 1
    otsu_edge_dilate: int = 0
    ws_blur: int = 3
    ws_footprint: int = 10
    ws_min_dist: float = 0.0
    ws_compactness: float = 0.0001
    slic_n: int = 50
    slic_compact: int = 1
    slic_sigma: int = 3

    # --- phase pre-segmentation ---------------------------------------------
    preseg_phase: str = "otsu"        # "otsu" | "adaptive"
    otsu_blur: int = 3
    otsu_offset: int = 0
    otsu_erode: int = 8
    otsu_dilate: int = 8
    adapt_block: int = 51
    adapt_c: int = 5
    adapt_erode: int = 0
    adapt_dilate: int = 0

    # --- ROI seed generation -------------------------------------------------
    roi_grain: str = "maxdt_interiors"   # maxdt_interiors|contour_interiors|contour_edges
    roi_phase: str = "maxdt"             # maxdt|contour
    width_thresh: PerTask = 10.0
    min_area: PerTask = 40
    grid_spacing: int = 32

    # --- SAM run -------------------------------------------------------------
    batch_size: int = 32
    multimask: bool = True
    mask_pick: str = "best"              # largest|smallest|best (of the 3 candidates)

    # --- mask screening ------------------------------------------------------
    min_score: PerTask = field(default_factory=lambda: [0.20, 0.10])
    min_mask_area: PerTask = field(default_factory=lambda: [50, 20])
    max_mask_frac: float = 0.60
    fill_grain_gaps: bool = True     # assign unclaimed pixels to nearest grain
                                     # (removes the black background in the map)

    # --- grain-map post-processing (each an independent toggle) --------------
    pp_despeckle: bool = False       # remove connected components < pp_min_grain_area
    pp_merge_fragments: bool = False # merge tiny fragments into longest-border neighbour
    pp_majority: bool = False        # modal-label smoothing in a pp_majority_size window
    pp_morph: bool = False           # per-grain opening+closing (disk pp_morph_radius)
    pp_min_grain_area: int = 30      # size threshold for despeckle / merge (px)
    pp_majority_size: int = 3        # majority-filter window (odd px)
    pp_morph_radius: int = 1         # morphological cleanup disk radius (px)

    # --- baselines -----------------------------------------------------------
    ws_footprint_base: int = 7
    adapt_block_base: int = 51
    adapt_c_base: int = 5
    min_grain_area: int = 10

    # --- grid resampling -----------------------------------------------------
    # Hex .ang scans are resampled onto a square grid (nearest-neighbour), like
    # the EBSD_ODF app. grid_ratio scales the square step: 1.0 = native hex step.
    # Square-grid scans are used as-is (no resampling) so results stay identical.
    grid_ratio: float = 1.0

    # --- input normalization -------------------------------------------------
    norm_lo: int = 1
    norm_hi: int = 99

    # --- display / export ----------------------------------------------------
    panel_h: float = 5.5
    kam_vmax: float = 3.0
    fig_dpi: int = 200
    save_format: str = "PNG"             # PNG | TIFF | SVG
    outfile: str = "matsam_result.png"

    # --- ground truth (optional metrics) ------------------------------------
    gt_grain: Optional[object] = None
    gt_phase: Optional[object] = None

    @property
    def sam2_dir(self) -> str:
        import os
        return os.path.join(self.model_dir, "sam2") if self.model_dir else ""


def per_task(val: PerTask, task: str):
    """scalar/len-1 -> same for all tasks; [grain, phase] -> pick by task."""
    import numpy as np
    if np.isscalar(val):
        return val
    seq = list(val)
    if len(seq) == 1:
        return seq[0]
    if len(seq) == 2:
        return seq[0] if task == "grain" else seq[1]
    raise ValueError(f"per-task param must be scalar, [x], or [grain, phase]; got {seq}")
