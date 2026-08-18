"""Figure builders — seed preview, comparison panels, overlay.

Every function returns a matplotlib Figure so it can be embedded in the GUI
canvas or saved to an image. No plt.show().
"""
from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure
from matplotlib.colors import ListedColormap
from skimage.metrics import adapted_rand_error
from skimage.segmentation import find_boundaries

from .config import Config
from .loader import MapData
from . import preseg as P


# ============================================================================
#  Bare single-image figures for SAVING: one image, no title, no axes, no
#  margins — just the pixels. Used by Step 5 "save each image separately".
# ============================================================================
def _bare_fig(arr, cmap=None, vmin=None, vmax=None, rgb=False):
    """Figure that is exactly the image, edge to edge (no axes/title/border)."""
    h, w = arr.shape[:2]
    fig = Figure(figsize=(w / 100.0, h / 100.0), dpi=100)
    fig._bare_image = True             # saveimg saves this with zero padding
    ax = fig.add_axes([0, 0, 1, 1])   # fill the whole figure
    ax.set_axis_off()
    if rgb:
        ax.imshow(arr, interpolation="nearest")
    else:
        ax.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    return fig


def bare_input(cfg: Config, md: MapData, task: str) -> Figure:
    """The raw SAM input image for a task (IQ, or composite for phase)."""
    from .loader import build_input
    img = build_input(cfg, md, task)
    return _bare_fig(img, cmap="gray", vmin=0, vmax=255)


def bare_grain(cfg: Config, result: dict) -> Figure:
    """Grain label map as a coloured image (each grain a random colour).

    Matches the on-screen version: integer labels indexed straight into the
    random colormap (label 0 -> black background)."""
    lab = result["grain"]
    return _bare_fig(lab, cmap=rand_cmap(int(lab.max())))


def bare_phase(cfg: Config, result: dict) -> Figure:
    """Phase mask as a black/white image."""
    return _bare_fig(result["phase"].astype(float), cmap="gray", vmin=0, vmax=1)


def _overlay_rgb(seeds: dict, result: dict) -> np.ndarray:
    """IQ background with whichever results are present: grain boundaries (cyan)
    and/or phase (red). Works for grain-only, phase-only, or both."""
    # base = the IQ input of whichever task ran (grain preferred, then phase)
    base = (seeds.get("grain") or seeds.get("phase"))["img"]
    rgb = np.stack([base] * 3, axis=-1).astype(float) / 255.0
    if "phase" in result:
        phase = result["phase"]
        rgb[phase] = 0.6 * rgb[phase] + 0.4 * np.array([1.0, 0.0, 0.0])   # red fill
    if "grain" in result:
        gb = find_boundaries(result["grain"], mode="outer")
        rgb[gb] = np.array([0.0, 1.0, 1.0])                               # cyan lines
    return rgb


def bare_overlay(cfg: Config, md: MapData, seeds: dict, result: dict) -> Figure:
    """Grain boundaries (cyan) and/or phase (red) over the IQ background — bare."""
    return _bare_fig(_overlay_rgb(seeds, result), rgb=True)


def _figsize(img_shape, ncols, panel_h, title_pad=0.6):
    h, w = img_shape[:2]
    ar = w / h
    return (panel_h * ar * ncols, panel_h + title_pad)


def _fig(img_shape, ncols, cfg: Config, constrained=True):
    layout = "constrained" if constrained else None
    return Figure(figsize=_figsize(img_shape, ncols, cfg.panel_h), layout=layout)


def _pack_panels(fig, wspace=0.04):
    """Pull a row of image panels tightly together.

    constrained-layout leaves each narrow panel centred in a wide slot, so for
    tall/narrow maps the panels drift far apart with big side gaps. Building the
    figure WITHOUT a layout engine (see _fig(constrained=False)) then packing
    with a small wspace puts them side by side — and avoids the "layout engine
    incompatible with subplots_adjust" warning.
    """
    fig.subplots_adjust(left=0.01, right=0.99, top=0.90, bottom=0.01,
                        wspace=wspace)
    fig._packed = True          # tell FigurePane.show_figure to leave this alone


def rand_cmap(n):
    rng = np.random.default_rng(0); c = rng.random((n + 1, 3)); c[0] = 0
    return ListedColormap(c)


def _miou(a, b):
    u = np.logical_or(a, b).sum()
    return np.logical_and(a, b).sum() / u if u else 0.0


def ari(pred, gt):
    are, _, _ = adapted_rand_error(gt.astype(int), pred.astype(int)); return 1 - are


def iou(pred, gt):
    return _miou(pred.astype(bool), gt.astype(bool))


# ---------------------------------------------------------------- input maps
def fig_input_maps(cfg: Config, md: MapData) -> Figure:
    # only plot KAM if it was actually computed (used for composite phase input)
    ncols = 3 if md.kam_arr is not None else 2
    fig = _fig(md.iq.shape, ncols, cfg, constrained=False); ax = fig.subplots(1, ncols)
    ax[0].imshow(md.iq, cmap="gray"); ax[0].set_title("IQ")
    ax[1].imshow(md.ci, cmap="gray"); ax[1].set_title("CI")
    if md.kam_arr is not None:
        ax[2].imshow(np.degrees(md.kam_arr), cmap="inferno", vmin=0, vmax=cfg.kam_vmax)
        ax[2].set_title(f"KAM (0-{cfg.kam_vmax:g} deg)")
    for a in ax:
        a.axis("off")
    _pack_panels(fig)
    return fig


# ---------------------------------------------------------------- seed preview
def fig_seeds(cfg: Config, S: dict) -> Figure:
    img, task = S["img"], S["task"]
    roi = np.array(S["roi"]) if S["roi"] else np.empty((0, 2))
    grid = np.array(S["grid"]) if S["grid"] else np.empty((0, 2))
    fig = _fig(img.shape, 5, cfg); ax = fig.subplots(1, 5)
    pm = cfg.preseg_grain if task == "grain" else cfg.preseg_phase
    titles = [f"Input\n({task})", f"Pre-seg\n({pm})", "Distance\ntransform",
              f"Grid only\n({len(grid)})", f"ROI+grid\n({len(roi)}R+{len(grid)}G)"]
    for a, t in zip(ax, titles):
        a.set_title(t, fontsize=8)
    ax[0].imshow(img, cmap="gray")
    ax[1].imshow(S["preseg"], cmap="gray")
    ax[2].imshow(S["dt"], cmap="hot")
    ax[3].imshow(img, cmap="gray")
    if len(grid): ax[3].scatter(grid[:, 0], grid[:, 1], c="lime", s=4)
    ax[4].imshow(img, cmap="gray")
    if len(grid): ax[4].scatter(grid[:, 0], grid[:, 1], c="lime", s=4)
    if len(roi): ax[4].scatter(roi[:, 0], roi[:, 1], c="red", s=7)
    for a in ax:
        a.axis("off")
    return fig


# ---------------------------------------------------------------- comparison
def fig_compare(cfg: Config, md: MapData, seeds: dict, result: dict, task: str) -> Figure:
    S = seeds[task]; img = S["img"]
    if task == "grain":
        panels = [("Input", img, "gray"),
                  ("MatSAM", result["grain"], "lab"),
                  ("OTSU", P.seg_otsu_grain(cfg, img)[0], "lab"),
                  ("Canny", P.seg_canny_grain(cfg, img)[0], "lab"),
                  ("Watershed", P.seg_watershed_grain(cfg, img)[0], "lab")]
    else:
        panels = [("Input", img, "gray"),
                  ("MatSAM", result["phase"], "bin"),
                  ("OTSU", P.seg_otsu_phase(cfg, img), "bin"),
                  ("Adaptive", P.seg_adaptive_phase(cfg, img), "bin")]
    fig = _fig(img.shape, len(panels), cfg); ax = fig.subplots(1, len(panels))
    for a, (name, im, kind) in zip(ax, panels):
        title = name
        if kind == "gray":
            a.imshow(im, cmap="gray"); title = f"Input ({task})"
        elif kind == "lab":
            a.imshow(im, cmap=rand_cmap(int(im.max())))
            if cfg.gt_grain is not None and name != "Input":
                title += f"\nARI={ari(im, cfg.gt_grain):.3f}"
        else:
            a.imshow(im, cmap="gray")
            if cfg.gt_phase is not None and name != "Input":
                title += f"\nIoU={iou(im, cfg.gt_phase):.3f}"
        a.set_title(title); a.axis("off")
    return fig


# ---------------------------------------------------------------- overlay
def fig_overlay(cfg: Config, md: MapData, seeds: dict, result: dict) -> Figure:
    """Input | (grain result) | overlay. Works for grain-only, phase-only, or both:
    the overlay panel shows grain boundaries (cyan) and/or phase (red) as present."""
    has_g = "grain" in result
    has_p = "phase" in result
    base = (seeds.get("grain") or seeds.get("phase"))["img"]
    rgb = _overlay_rgb(seeds, result)

    panels = [("Input (IQ)", ("gray", base))]
    if has_g:
        panels.append(("Grains", ("lab", result["grain"])))
    elif has_p:
        panels.append(("Phase", ("bin", result["phase"])))
    if has_g and has_p:
        panels.append(("GB (cyan) + phase (red)", ("rgb", rgb)))
    elif has_g:
        panels.append(("GB overlay (cyan)", ("rgb", rgb)))
    else:
        panels.append(("Phase overlay (red)", ("rgb", rgb)))

    fig = _fig(base.shape, len(panels), cfg); ax = np.atleast_1d(fig.subplots(1, len(panels)))
    for a, (title, (kind, im)) in zip(ax, panels):
        if kind == "gray":
            a.imshow(im, cmap="gray")
        elif kind == "lab":
            a.imshow(im, cmap=rand_cmap(int(im.max())))
        elif kind == "bin":
            a.imshow(im, cmap="gray", vmin=0, vmax=1)
        else:
            a.imshow(im)
        a.set_title(title); a.axis("off")
    return fig
