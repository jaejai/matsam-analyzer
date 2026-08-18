"""Unified multi-format EBSD point-data reader.

Reads .ang (text), .osc (EDAX binary), and orix-supported .ctf / h5ebsd into one
(n, >=8) table with .ang column order:
    0:phi1 1:PHI 2:phi2 3:x 4:y 5:IQ 6:CI 7:phase   (Euler radians, Bunge/TSL)

Also returns per-phase metadata (id, name, point group, lattice) and the
dominant crystal point group. The .osc reader is ported from MTEX's BSD-licensed
loadEBSD_osc.m (Osc2Ang, Pilchak/Shiveley, USAFRL); verified against matching
.ang files (identical point count and euler/x/y/CI to float32 precision, same
symmetry code). This module is the standalone twin of the notebook's `oscreader`
cell in EBSD_ODF_combined_kikuchipy.ipynb.
"""
from __future__ import annotations

import os as _os
import re as _re

import numpy as np

_OSC_START = bytes([0xB9, 0x0B, 0xEF, 0xFF, 0x02, 0x00, 0x00, 0x00])
_OSC_HS = bytes([0xB9, 0x0B, 0xEF, 0xFF, 0x01, 0x00, 0x00, 0x00])

# TSL/EDAX symmetry code -> orix Laue point-group string. The same integer code
# appears in the .ang '# Symmetry NN' line and the .osc header laueGroup int32.
_TSL_SYM = {43: "m-3m", 23: "m-3", 62: "6/mmm", 6: "6/m", 42: "4/mmm", 4: "4/m",
            32: "-3m", 3: "-3", 22: "mmm", 2: "2/m", 1: "-1"}
# orix proper-group name -> Laue class (for the orix path).
_PROPER_TO_LAUE = {"432": "m-3m", "23": "m-3", "622": "6/mmm", "6": "6/m",
                   "32": "-3m", "3": "-3", "422": "4/mmm", "4": "4/m",
                   "222": "mmm", "2": "2/m", "1": "-1"}


# --------------------------------------------------------------------------
# single-phase symmetry helpers
# --------------------------------------------------------------------------
def _sym_from_ang(path):
    with open(path) as f:
        for line in f:
            s = line.strip()
            if not s.startswith("#"):
                break
            m = _re.match(r"#\s*Symmetry\s+(\d+)", s)
            if m:
                return _TSL_SYM.get(int(m.group(1)))
    return None


def _sym_from_osc(buf):
    i0, i1 = buf.find(_OSC_HS), buf.find(_OSC_START)
    if i0 < 0 or i1 < 0:
        return None
    hb = buf[i0 + 8:i1]
    # laueGroup int32 sits 256 B into a phase block; scan for a known code whose
    # following 24 B parse as a valid lattice (self-validating, per MTEX layout).
    for off in range(0, len(hb) - 288):
        code = int(np.frombuffer(hb[off + 256:off + 260], dtype="<i4")[0])
        if code in _TSL_SYM:
            ax = np.frombuffer(hb[off + 260:off + 272], dtype="<f4")
            an = np.frombuffer(hb[off + 272:off + 284], dtype="<f4")
            if np.all(ax > 0) and np.all(ax < 100) and np.all(an > 0) and np.all(an < 180):
                return _TSL_SYM[code]
    return None


# --------------------------------------------------------------------------
# all-phase metadata (id, name, point group, lattice)
# --------------------------------------------------------------------------
def _phases_from_ang(path):
    phases, cur = [], None
    with open(path) as f:
        for line in f:
            s = line.strip()
            if not s.startswith("#"):
                break
            body = s[1:].strip()
            m = _re.match(r"Phase\s+(\d+)", body)
            if m:
                if cur:
                    phases.append(cur)
                cur = {"id": int(m.group(1)), "name": None,
                       "point_group": None, "lattice": None}
                continue
            if cur is None:
                continue
            if body.startswith("MaterialName"):
                parts = body.split(None, 1)
                cur["name"] = parts[1].strip() if len(parts) > 1 else None
            elif body.startswith("Symmetry"):
                mm = _re.search(r"Symmetry\s+(\d+)", body)
                if mm:
                    cur["point_group"] = _TSL_SYM.get(int(mm.group(1)))
            elif body.startswith("LatticeConstants"):
                nums = [float(x) for x in _re.findall(r"[-+]?\d*\.?\d+", body)]
                if len(nums) >= 6:
                    cur["lattice"] = tuple(nums[:6])
        if cur:
            phases.append(cur)
    return phases


def _phases_from_osc(path):
    with open(path, "rb") as _f:
        buf = _f.read()
    i0, i1 = buf.find(_OSC_HS), buf.find(_OSC_START)
    if i0 < 0 or i1 < 0:
        return []
    hb = buf[i0 + 8:i1]
    out, off, pid = [], 0, 1
    while off < len(hb) - 288:
        code = int(np.frombuffer(hb[off + 256:off + 260], dtype="<i4")[0])
        if code in _TSL_SYM:
            ax = np.frombuffer(hb[off + 260:off + 272], dtype="<f4")
            an = np.frombuffer(hb[off + 272:off + 284], dtype="<f4")
            if np.all(ax > 0) and np.all(ax < 100) and np.all(an > 0) and np.all(an < 180):
                out.append({"id": pid, "name": None, "point_group": _TSL_SYM[code],
                            "lattice": tuple(float(v) for v in ax) + tuple(float(v) for v in an)})
                pid += 1
                off += 284
                continue
        off += 1
    return out


def _phases_from_orix_xmap(xmap):
    out = []
    for pid, ph in xmap.phases:
        if ph.point_group is None:
            continue
        nm = ph.point_group.name
        lat = None
        if ph.structure is not None and ph.structure.lattice is not None:
            L = ph.structure.lattice
            lat = (L.a, L.b, L.c, L.alpha, L.beta, L.gamma)
        out.append({"id": int(pid), "name": ph.name,
                    "point_group": _PROPER_TO_LAUE.get(nm, nm), "lattice": lat})
    return out


def lattice_kind(lat, name=""):
    """Rough FCC/BCC/HCP guess from lattice + name, for component overlays only."""
    nm = (name or "").lower()
    if lat is not None and abs(lat[3] - 90) < 1 and abs(lat[5] - 120) < 1:
        return "HCP"
    for k in ("austen", "gamma", "fcc", "ag", "cu", "ni", "al"):
        if k in nm:
            return "FCC"
    for k in ("ferrit", "martens", "alpha", "bcc", "fe"):
        if k in nm:
            return "BCC"
    return "BCC"


# --------------------------------------------------------------------------
# per-format point readers
# --------------------------------------------------------------------------
def read_osc(path):
    """EDAX .osc -> (data[n,ncol] float64, xstep, ystep, crystal_sym). Radians."""
    with open(path, "rb") as f:
        buf = f.read()
    header = np.frombuffer(buf, dtype="<u4", count=8)
    n = int(header[6])
    idx = buf.find(_OSC_START)
    if idx < 0:
        raise ValueError("osc: data-start marker not found")
    pos = idx + 8
    dn = int(np.frombuffer(buf, dtype="<u4", count=1, offset=pos)[0])
    if round(((dn / 4 - 2) / 10) / n) == 1:
        pos += 4
    vals = np.frombuffer(buf, dtype="<f4", count=3, offset=pos)
    xstep = float(vals[0])
    if xstep == 0.0:
        xstep, ystep = float(vals[1]), float(vals[2]); pos += 12
    else:
        ystep = float(vals[1]); pos += 8
    sym = _sym_from_osc(buf)
    for ncol in range(5, 31):
        need = n * ncol
        block = np.frombuffer(buf, dtype="<f4", count=need, offset=pos)
        if block.size < need:
            continue
        cand = block.reshape(n, ncol)
        if (round(float(cand[1, 3]), 4) == round(xstep, 4)
                and round(float(cand[1, 4]), 4) == 0.0):
            return cand.astype(np.float64), xstep, ystep, sym
    raise ValueError("osc: could not resolve column count (5..30)")


def read_ang(path, comment_char="#"):
    with open(path) as f:
        rows = [l for l in f
                if not l.strip().startswith(comment_char) and l.strip()]
    return np.loadtxt(rows), _sym_from_ang(path)


def read_via_orix(path, xmap=None):
    from orix.io import load
    if xmap is None:
        xmap = load(path)
    e = xmap.rotations.to_euler()
    if e.ndim == 3:
        e = e[:, 0, :]
    x = np.asarray(xmap.x, float); y = np.asarray(xmap.y, float)
    prop = xmap.prop
    iq = np.asarray(prop.get("iq", np.zeros(xmap.size)), float)
    ci = np.asarray(prop.get("ci", prop.get("confidence_index",
                                            np.zeros(xmap.size))), float)
    phase = np.asarray(xmap.phase_id, float)
    sym = None
    for _pid, _ph in xmap.phases:
        if _ph.point_group is not None:
            nm = _ph.point_group.name
            sym = _PROPER_TO_LAUE.get(nm, nm); break
    data = np.column_stack([e[:, 0], e[:, 1], e[:, 2], x, y, iq, ci, phase])
    return data, sym


_ORIX_EXT = {".ctf", ".h5", ".oh5", ".hdf5", ".hdf", ".dream3d"}


def read_ebsd(path, comment_char="#"):
    """Dispatch by extension -> (data[n,>=8] float64, meta).

    meta = {format, xstep, ystep, crystal_sym, phases}. Euler columns (0..2) are
    radians, Bunge/TSL. Columns follow the .ang order.
    """
    ext = _os.path.splitext(path)[1].lower()
    meta = {"format": ext, "xstep": None, "ystep": None,
            "crystal_sym": None, "phases": []}
    if ext == ".ang":
        data, sym = read_ang(path, comment_char)
        meta["crystal_sym"] = sym
        meta["phases"] = _phases_from_ang(path)
        return data, meta
    if ext == ".osc":
        data, xs, ys, sym = read_osc(path)
        meta.update(xstep=xs, ystep=ys, crystal_sym=sym)
        meta["phases"] = _phases_from_osc(path)
        return data, meta
    if ext in _ORIX_EXT:
        from orix.io import load as _load
        xmap = _load(path)
        data, sym = read_via_orix(path, xmap=xmap)
        meta["crystal_sym"] = sym
        meta["phases"] = _phases_from_orix_xmap(xmap)
        return data, meta
    raise ValueError(f"unsupported EBSD format: {ext!r}")
