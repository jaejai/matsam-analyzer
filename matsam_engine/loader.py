"""Load EBSD .ang + derived maps (IQ, CI, KAM) and build the SAM input channel.

Ports notebook sections §1 and §2 (matsam_sam2.ipynb).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from .config import Config


@dataclass
class MapData:
    H: int = 0
    W: int = 0
    iq: np.ndarray = None
    ci: np.ndarray = None
    kam_arr: np.ndarray = None
    kam_max: np.ndarray = None


def _is_hex(x, y) -> bool:
    """Detect a hexagonal grid: adjacent rows are staggered by ~half a step in x.

    In a TSL hex scan, even/odd rows are offset by hex_step/2 in x. A square grid
    has every row starting at the same x. We compare the smallest x of the first
    two rows; a shift of a meaningful fraction of the step means hex.
    """
    y_uniq = np.unique(np.round(y, 6))
    if len(y_uniq) < 2:
        return False
    dy = np.median(np.diff(y_uniq))
    r0 = x[np.abs(y - y_uniq[0]) < 0.05 * dy]
    r1 = x[np.abs(y - y_uniq[1]) < 0.05 * dy]
    if r0.size == 0 or r1.size == 0:
        return False
    row0 = np.sort(r0)
    step = np.median(np.diff(row0)) if row0.size > 1 else dy
    shift = abs(r0.min() - r1.min())
    # square: shift ~0 ; hex: shift ~ step/2
    return shift > 0.2 * step


def _regrid_hex(cfg, raw, log):
    """Nearest-neighbour resample a hex .ang onto a square grid (EBSD_ODF §2).

    raw columns: 0-2 phi1/PHI/phi2, 3 x, 4 y, 5 iq, 6 ci, 7 phase, 8 sem, 9 fit.
    Returns (H, W, iq, ci, euler, nn_idx) where euler is the square-grid Euler
    angles (H*W, 3) for optional KAM.
    """
    from scipy.spatial import cKDTree
    x_hex, y_hex = raw[:, 3], raw[:, 4]
    y_uniq = np.unique(np.round(y_hex, 6))
    row0 = np.sort(x_hex[np.abs(y_hex - y_uniq[0]) < 0.05 * np.median(np.diff(y_uniq))])
    hex_step = np.median(np.diff(row0))
    step = hex_step * cfg.grid_ratio

    x1d = np.arange(x_hex.min(), x_hex.max() + step * 0.5, step)
    y1d = np.arange(y_hex.min(), y_hex.max() + step * 0.5, step)
    nx, ny = len(x1d), len(y1d)
    gx, gy = np.meshgrid(x1d, y1d)
    tree = cKDTree(np.column_stack([x_hex, y_hex]))
    _, nn_idx = tree.query(np.column_stack([gx.ravel(), gy.ravel()]))

    iq = raw[nn_idx, 5].reshape(ny, nx)
    ci = raw[nn_idx, 6].reshape(ny, nx)
    euler = np.column_stack([raw[nn_idx, 0], raw[nn_idx, 1], raw[nn_idx, 2]])
    log(f"hex grid -> square {ny}x{nx} @ {step:.4f} um/px (grid_ratio={cfg.grid_ratio})")
    return ny, nx, iq, ci, euler


def load_maps(cfg: Config, log=print) -> MapData:
    from orix.crystal_map import CrystalMap
    from orix.quaternion import Rotation, Orientation
    from orix.quaternion.symmetry import Oh

    data = np.loadtxt(cfg.ang_file)
    # KAM is needed only for the composite input channel (IQ x (1-KAM)); it now
    # applies to grain and/or phase, so compute it whenever composite is chosen.
    need_kam = (cfg.input_channel == "composite")

    if _is_hex(data[:, 3], data[:, 4]):
        # --- hexagonal scan: resample to a square grid (KD-tree NN) -----------
        H, W, iq, ci, euler = _regrid_hex(cfg, data, log)
        if not need_kam:
            log("KAM skipped (not used for this task/input)")
            return MapData(H=H, W=W, iq=iq, ci=ci, kam_arr=None, kam_max=None)
        # orientations from the RESAMPLED square-grid Euler angles
        ori = Orientation.from_euler(euler, symmetry=Oh).reshape(H, W)
        kam_arr, kam_max = _kam(ori, H, W)
        log(f"KAM mean {np.degrees(kam_arr.mean()):.2f} deg")
        return MapData(H=H, W=W, iq=iq, ci=ci, kam_arr=kam_arr, kam_max=kam_max)

    # --- square scan: original orix reshape path (unchanged) ------------------
    xmap = CrystalMap(
        rotations=Rotation.from_euler(data[:, 0:3]),
        x=data[:, 3], y=data[:, 4],
        phase_id=data[:, 7].astype(int),
        prop={"iq": data[:, 5], "ci": data[:, 6],
              "sem": data[:, 8], "fit": data[:, 9]},
    )
    H, W = xmap.shape
    iq = xmap.prop["iq"].reshape(xmap.shape, order="F")
    ci = xmap.prop["ci"].reshape(xmap.shape, order="F")
    log(f"map shape: {xmap.shape}")

    # KAM is only needed for the composite input channel (IQ x (1-KAM)).
    # For input_channel="iq", skip the expensive 8-neighbour computation.
    if not need_kam:
        log("KAM skipped (not used for this task/input)")
        return MapData(H=H, W=W, iq=iq, ci=ci, kam_arr=None, kam_max=None)

    try:
        ori = Orientation(xmap.rotations, symmetry=Oh).reshape(H, W, order="F")
    except TypeError:
        flat = Orientation(xmap.rotations, symmetry=Oh)
        idx = np.arange(H * W).reshape(H, W, order="F")
        ori = flat[idx.ravel()].reshape(H, W)

    kam_arr, kam_max = _kam(ori, H, W)
    log(f"KAM mean {np.degrees(kam_arr.mean()):.2f} deg")
    return MapData(H=H, W=W, iq=iq, ci=ci, kam_arr=kam_arr, kam_max=kam_max)


def _kam(ori, H, W):
    """8-neighbour misorientation: median (KAM) and max, in radians."""
    neighbor_angles = np.full((H, W, 8), np.nan, np.float32)
    n = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            cy = slice(max(0, -dy), H + min(0, -dy)); cx = slice(max(0, -dx), W + min(0, -dx))
            ny = slice(max(0, dy), H + min(0, dy)); nx = slice(max(0, dx), W + min(0, dx))
            neighbor_angles[cy, cx, n] = ori[cy, cx].angle_with(ori[ny, nx]); n += 1
    return np.nanmedian(neighbor_angles, axis=2), np.nanmax(neighbor_angles, axis=2)


# --- input-channel builder (§2) ---------------------------------------------
def norm01(a, cfg: Config):
    vmin, vmax = np.percentile(a, [cfg.norm_lo, cfg.norm_hi])
    return np.clip((a - vmin) / (vmax - vmin + 1e-10), 0, 1)


def to_u8(a01):
    return (a01 * 255).astype(np.uint8)


def build_input(cfg: Config, md: MapData, task: str) -> np.ndarray:
    # "input_channel" (IQ | composite) applies to BOTH grain and phase.
    # composite = IQ x (1 - KAM): darkens high-misorientation regions (martensite).
    if cfg.input_channel == "composite" and md.kam_arr is not None:
        return to_u8(norm01(md.iq, cfg) * (1.0 - norm01(md.kam_arr, cfg)))
    return to_u8(norm01(md.iq, cfg))


def rgb_for_sam(img_u8):
    from PIL import Image
    return Image.fromarray(np.stack([img_u8] * 3, axis=-1))
