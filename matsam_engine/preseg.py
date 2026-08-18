"""Rule-based pre-segmentation, seed finding, and baselines.

Global config/params are passed via Config; H/W via MapData.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.filters import threshold_otsu
from skimage.measure import label as sk_label, regionprops
from skimage.morphology import remove_small_objects, remove_small_holes
from skimage.segmentation import watershed, slic, find_boundaries
from skimage.feature import peak_local_max

from .config import Config, per_task
from .loader import MapData


# ===================== shared morphology helper =====================
def _morph(binary, min_size=0, erode=0, dilate=0):
    b = binary
    if min_size:
        b = remove_small_objects(b, max_size=min_size)   # max_size=N == old min_size=N
    b = b.astype(np.uint8)
    if erode:
        b = cv2.erode(b, np.ones((erode, erode), np.uint8))
    if dilate:
        b = cv2.dilate(b, np.ones((dilate, dilate), np.uint8))
    return b.astype(bool)


# ===================== GRAIN pre-seg (boundary map) =====================
def _watershed_labels(cfg: Config, img_u8):
    g = cv2.GaussianBlur(img_u8, (cfg.ws_blur, cfg.ws_blur), 0) if cfg.ws_blur else img_u8
    fg = g < threshold_otsu(g)
    dt = distance_transform_edt(~fg if fg.mean() > 0.5 else fg)
    coords = peak_local_max(dt, min_distance=cfg.ws_footprint,
                            threshold_abs=cfg.ws_min_dist * dt.max())
    markers = np.zeros(dt.shape, int)
    for i, (r, cc) in enumerate(coords, 1):
        markers[r, cc] = i
    grad = cv2.GaussianBlur(img_u8.astype(np.float32) / 255.0, (3, 3), 0)
    gx = cv2.Sobel(grad, cv2.CV_32F, 1, 0, 3)
    gy = cv2.Sobel(grad, cv2.CV_32F, 0, 1, 3)
    elevation = np.hypot(gx, gy)
    return watershed(elevation, markers, compactness=cfg.ws_compactness)


def grain_edges(cfg: Config, img_u8, method):
    if method == "canny":
        g = cv2.GaussianBlur(img_u8, (cfg.canny_blur, cfg.canny_blur), 0) if cfg.canny_blur else img_u8
        e = cv2.Canny(g, cfg.canny_lo, cfg.canny_hi) > 0
        return _morph(e, cfg.canny_min_size, cfg.canny_erode, cfg.canny_dilate)
    if method == "otsu_edge":
        g = cv2.GaussianBlur(img_u8, (cfg.otsu_edge_blur, cfg.otsu_edge_blur), 0) if cfg.otsu_edge_blur else img_u8
        t = threshold_otsu(g) + cfg.otsu_edge_offset
        e = g < t
        return _morph(e, cfg.otsu_edge_min_size, cfg.otsu_edge_erode, cfg.otsu_edge_dilate)
    if method == "watershed":
        return find_boundaries(_watershed_labels(cfg, img_u8), mode="outer")
    if method == "slic":
        labels = slic(img_u8, n_segments=cfg.slic_n, compactness=cfg.slic_compact,
                      sigma=cfg.slic_sigma, channel_axis=None, start_label=1)
        return find_boundaries(labels, mode="outer")
    raise ValueError(f"preseg_grain must be otsu_edge|canny|watershed|slic, got {method}")


# ===================== PHASE pre-seg (foreground map) =====================
def phase_fg(cfg: Config, img_u8, method):
    if method == "otsu":
        g = cv2.GaussianBlur(img_u8, (cfg.otsu_blur, cfg.otsu_blur), 0) if cfg.otsu_blur else img_u8
        t = threshold_otsu(g) + cfg.otsu_offset
        fg = g < t
        return _morph(fg, 0, cfg.otsu_erode, cfg.otsu_dilate)
    if method == "adaptive":
        blk = cfg.adapt_block | 1
        fg = cv2.adaptiveThreshold(img_u8, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, blk, cfg.adapt_c) > 0
        return _morph(fg, 0, cfg.adapt_erode, cfg.adapt_dilate)
    raise ValueError(f"preseg_phase must be otsu|adaptive, got {method}")


# ===================== seed finders =====================
def _seed_contour(binary):
    b = (binary.astype(np.uint8)) * 255
    contours, _ = cv2.findContours(b, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)
    pts = []
    for cnt in contours:
        M = cv2.moments(cnt)
        if M["m00"] != 0:
            pts.append([int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])])
    return pts


def _seed_maxdt(cfg: Config, binary, task):
    wt = per_task(cfg.width_thresh, task)
    ma = per_task(cfg.min_area, task)
    dt = distance_transform_edt(binary)
    lab = sk_label(dt >= wt)
    pts = []
    for p in regionprops(lab, intensity_image=dt):
        if p.area < ma:
            continue
        comp = (lab == p.label)
        my, mx = np.unravel_index((dt * comp).argmax(), dt.shape)
        pts.append([int(mx), int(my)])
    return pts


# ===================== baselines (no SAM) =====================
def _interiors_to_labels(cfg: Config, edge_bool):
    lab = sk_label(~edge_bool, connectivity=1)
    out = np.zeros_like(lab); keep = 1
    for p in regionprops(lab):
        if p.area >= cfg.min_grain_area:
            out[lab == p.label] = keep; keep += 1
    return out


def seg_canny_grain(cfg, img_u8):
    e = grain_edges(cfg, img_u8, "canny")
    return _interiors_to_labels(cfg, e), e


def seg_otsu_grain(cfg, img_u8):
    e = img_u8 < threshold_otsu(img_u8)
    return _interiors_to_labels(cfg, e), e


def seg_watershed_grain(cfg, img_u8):
    lab = _watershed_labels(cfg, img_u8)
    out = np.zeros_like(lab); keep = 1
    for p in regionprops(lab):
        if p.area >= cfg.min_grain_area:
            out[lab == p.label] = keep; keep += 1
    return out, find_boundaries(lab, mode="outer")


def seg_otsu_phase(cfg, img_u8, dark_fg=True):
    a = per_task(cfg.min_mask_area, "phase")
    t = threshold_otsu(img_u8)
    fg = img_u8 < t if dark_fg else img_u8 > t
    fg = remove_small_holes(remove_small_objects(fg, max_size=a), max_size=a)
    return fg


def seg_adaptive_phase(cfg, img_u8, dark_fg=True):
    a = per_task(cfg.min_mask_area, "phase")
    blk = cfg.adapt_block | 1
    tt = cv2.THRESH_BINARY_INV if dark_fg else cv2.THRESH_BINARY
    fg = cv2.adaptiveThreshold(img_u8, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, tt, blk, cfg.adapt_c) > 0
    fg = remove_small_holes(remove_small_objects(fg, max_size=a), max_size=a)
    return fg


# ===================== make_seeds =====================
def make_seeds(cfg: Config, md: MapData, img_u8, task, log=print):
    H, W = md.H, md.W
    if task == "grain":
        mode = cfg.roi_grain
        edges = grain_edges(cfg, img_u8, cfg.preseg_grain)
        preseg = edges
        dt = distance_transform_edt(~edges)
        if mode == "contour_edges":
            roi = _seed_contour(edges)
        elif mode == "contour_interiors":
            roi = _seed_contour(~edges)
        elif mode == "maxdt_interiors":
            roi = _seed_maxdt(cfg, ~edges, task)
        else:
            raise ValueError(f"roi_grain invalid: {mode}")
    else:
        mode = cfg.roi_phase
        regions = phase_fg(cfg, img_u8, cfg.preseg_phase)
        preseg = regions
        dt = distance_transform_edt(regions)
        if mode == "maxdt":
            roi = _seed_maxdt(cfg, regions, task)
        elif mode == "contour":
            roi = _seed_contour(regions)
        else:
            raise ValueError(f"roi_phase invalid: {mode}")

    gs = cfg.grid_spacing
    grid = [[gx, gy]
            for gy in range(gs // 2, H, gs)
            for gx in range(gs // 2, W, gs)]
    if roi:
        arr = np.array(roi); mind = gs // 2
        grid_kept = [g for g in grid if np.sqrt(((arr - g) ** 2).sum(1)).min() > mind]
    else:
        grid_kept = grid

    pts = list(roi) + list(grid_kept)
    log(f"[{task}] seeds: {len(pts)} ({len(roi)} ROI + {len(grid_kept)} grid) | mode={mode}")
    return {"img": img_u8, "task": task, "pts": pts, "roi": roi,
            "grid": grid_kept, "n_roi": len(roi), "preseg": preseg, "dt": dt}
