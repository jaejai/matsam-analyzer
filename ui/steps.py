"""Per-step parameter panels and result panes for the MatSAM GUI (5 steps).

Every tunable Config field is exposed. Rarely-touched / method-specific params
live under a collapsible "Advanced" section per step.

  build_step_controls(win, n) -> (page, ctrls)
  build_step_results(win, n)  -> (page, refs)
  read_all_controls(win)      -> Config
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QPushButton, QCheckBox, QFileDialog, QPlainTextEdit, QFrame,
)

from matsam_engine import Config
from .widgets import (SectionLabel, SegGroup, ChipButton, FigurePane, StatCard,
                      ParamLabel, StepSpinBox, StepDoubleSpinBox)


# ------------------------------------------------------------------ helpers
def _widget_for(w):
    """A StepSpin(Double)Box lives inside a +/- row container; add that to the
    layout (not the bare spinbox). Everything else is added as-is."""
    return w.row() if hasattr(w, "row") else w


def _row(label, w):
    box = QVBoxLayout(); box.setSpacing(4); box.setContentsMargins(0, 0, 0, 0)
    box.addWidget(ParamLabel(label.upper())); box.addWidget(_widget_for(w))
    cont = QWidget(); cont.setObjectName("RowCont"); cont.setLayout(box)
    return cont


def _dsb(lo, hi, val, step=1.0, dec=2):
    s = StepDoubleSpinBox(); s.setRange(lo, hi); s.setValue(val); s.setSingleStep(step); s.setDecimals(dec); return s


def _sb(lo, hi, val, step=1):
    s = StepSpinBox(); s.setRange(lo, hi); s.setValue(val); s.setSingleStep(step); return s


def _two(a, b):
    r = QHBoxLayout(); r.addWidget(a); r.addWidget(b); w = QWidget(); w.setObjectName("RowCont"); w.setLayout(r); return w


def _adv(lay):
    """Add an 'Advanced' expander to lay; returns the (hidden) body VBox layout."""
    div = QFrame(); div.setFrameShape(QFrame.HLine)
    div.setStyleSheet("color:rgba(255,255,255,0.07);"); lay.addWidget(div)
    btn = QPushButton("▶  ADVANCED"); btn.setObjectName("AdvToggle")
    btn.setStyleSheet("text-align:left;border:none;background:transparent;color:#9fc3ff;"
                      "font:800 11px Consolas;letter-spacing:1px;padding:8px 2px;")
    btn.setCheckable(True)
    body = QWidget(); body.setObjectName("RowCont"); body.setVisible(False)
    bl = QVBoxLayout(body); bl.setContentsMargins(0, 8, 0, 0); bl.setSpacing(11)
    def tog():
        body.setVisible(btn.isChecked())
        btn.setText("▼  ADVANCED" if btn.isChecked() else "▶  ADVANCED")
    btn.clicked.connect(tog)
    lay.addWidget(btn); lay.addWidget(body)
    return bl


# ================================================================= CONTROLS
def build_step_controls(win, n):
    page = QWidget(); page.setObjectName("ParamPage")
    lay = QVBoxLayout(page); lay.setContentsMargins(0, 6, 0, 0); lay.setSpacing(13)
    c = {}
    d = Config()

    # ------------------------------------------------------------- STEP 1
    if n == 1:
        ang = QLineEdit(); ang.setPlaceholderText("Select an EBSD scan file ...")
        browse = QPushButton("Browse"); browse.setObjectName("BrowseBtn")
        def pick():
            import os
            from app import ROOT
            sd = ROOT
            filt = ("EBSD scan files (*.ang *.osc *.ctf *.h5 *.oh5 *.hdf5 *.hdf *.dream3d);;"
                    "TSL/EDAX text (*.ang);;EDAX OIM binary (*.osc);;"
                    "HKL Channel 5 (*.ctf);;HDF5 / h5ebsd (*.h5 *.oh5 *.hdf5 *.hdf *.dream3d);;"
                    "All files (*)")
            p, _ = QFileDialog.getOpenFileName(win, "Open EBSD scan", sd, filt)
            if p:
                ang.setText(p); win.file_chip.setText(os.path.basename(p))
        browse.clicked.connect(pick)
        fr = QHBoxLayout(); fr.setSpacing(7); fr.addWidget(ang, 1); fr.addWidget(browse)
        fw = QWidget(); fw.setObjectName("RowCont"); fw.setLayout(fr)
        lay.addWidget(_row("EBSD scan (.ang / .osc / .ctf / h5ebsd)", fw)); c["ang"] = ang
        c["task"] = SegGroup([("grain", "grain"), ("phase", "phase"), ("both", "both")], default=d.task)
        lay.addWidget(_row("Task", c["task"]))
        c["input_channel"] = SegGroup([("iq", "IQ"), ("composite", "composite")], default=d.input_channel)
        lay.addWidget(_row("Input channel (grain + phase)", c["input_channel"]))
        c["gpu_index"] = _sb(0, 8, d.gpu_index)
        lay.addWidget(_row("GPU index", c["gpu_index"]))

        # --- crop before MatSAM (drag on the map, or type numbers) -----------
        c["crop_enabled"] = QCheckBox("Crop before analysis")
        c["crop_enabled"].setChecked(d.crop_enabled)
        c["crop_enabled"].setStyleSheet("color:#dbe4ef; font-size:12px;")
        lay.addWidget(c["crop_enabled"])
        c["crop_x"] = _sb(0, 100000, d.crop_x); c["crop_y"] = _sb(0, 100000, d.crop_y)
        c["crop_w"] = _sb(0, 100000, d.crop_w); c["crop_h"] = _sb(0, 100000, d.crop_h)
        lay.addWidget(_two(_row("Crop X [px]", c["crop_x"]), _row("Crop Y [px]", c["crop_y"])))
        lay.addWidget(_two(_row("Crop W [px] (0=edge)", c["crop_w"]),
                           _row("Crop H [px] (0=edge)", c["crop_h"])))
        _hint = QLabel("Tip: drag on the IQ map to draw the crop; the boxes update live.")
        _hint.setStyleSheet("color:#9fb0c4; font-size:10px; font-style:italic; background:transparent;")
        _hint.setWordWrap(True); lay.addWidget(_hint)
        win._crop_ctrls = c   # so the map pane can push drag rectangles back here

        adv = _adv(lay)
        c["grid_ratio"] = _dsb(0.25, 4.0, d.grid_ratio, 0.25, 2)
        c["kam_vmax"] = _dsb(0.5, 15, d.kam_vmax, 0.5, 1)
        c["norm_lo"] = _sb(0, 49, d.norm_lo); c["norm_hi"] = _sb(51, 100, d.norm_hi)
        adv.addWidget(_row("Grid ratio (hex→square; 1.0 = native)", c["grid_ratio"]))
        adv.addWidget(_row("KAM display vmax [deg]", c["kam_vmax"]))
        adv.addWidget(_two(_row("Norm low %ile", c["norm_lo"]), _row("Norm high %ile", c["norm_hi"])))

    # ------------------------------------------------------------- STEP 2
    elif n == 2:
        c["preseg_grain"] = QComboBox(); c["preseg_grain"].addItems(["watershed", "canny", "otsu_edge", "slic"])
        c["preseg_grain"].setCurrentText(d.preseg_grain)
        lay.addWidget(_row("Grain pre-seg method", c["preseg_grain"]))
        c["preseg_phase"] = QComboBox(); c["preseg_phase"].addItems(["otsu", "adaptive"])
        c["preseg_phase"].setCurrentText(d.preseg_phase)
        lay.addWidget(_row("Phase pre-seg method", c["preseg_phase"]))
        c["roi_grain"] = QComboBox(); c["roi_grain"].addItems(["maxdt_interiors", "contour_interiors", "contour_edges"])
        c["roi_grain"].setCurrentText(d.roi_grain)
        c["roi_phase"] = QComboBox(); c["roi_phase"].addItems(["maxdt", "contour"])
        c["roi_phase"].setCurrentText(d.roi_phase)
        lay.addWidget(_two(_row("ROI (grain)", c["roi_grain"]), _row("ROI (phase)", c["roi_phase"])))
        c["grid_spacing"] = _sb(4, 128, d.grid_spacing); c["min_area"] = _sb(1, 2000, int(d.min_area))
        lay.addWidget(_two(_row("Grid spacing", c["grid_spacing"]), _row("Min ROI area", c["min_area"])))
        c["width_thresh"] = _dsb(1, 50, float(d.width_thresh), 0.5, 1)
        lay.addWidget(_row("Width thresh (px)", c["width_thresh"]))
        note = QLabel("These change the SEEDS → re-running invalidates the SAM step.")
        note.setStyleSheet("color:#f0c674;font:11px Consolas;background:transparent;"); note.setWordWrap(True)
        lay.addWidget(note)

        adv = _adv(lay)
        # --- watershed ---
        adv.addWidget(ParamLabel("WATERSHED"))
        c["ws_blur"] = _sb(0, 15, d.ws_blur); c["ws_footprint"] = _sb(2, 60, d.ws_footprint)
        adv.addWidget(_two(_row("WS blur", c["ws_blur"]), _row("WS footprint", c["ws_footprint"])))
        c["ws_min_dist"] = _dsb(0, 1, d.ws_min_dist, 0.05, 2); c["ws_compactness"] = _dsb(0, 1, d.ws_compactness, 0.0001, 4)
        adv.addWidget(_two(_row("WS min dist", c["ws_min_dist"]), _row("WS compactness", c["ws_compactness"])))
        # --- canny ---
        adv.addWidget(ParamLabel("CANNY"))
        c["canny_blur"] = _sb(0, 15, d.canny_blur); c["canny_lo"] = _sb(0, 500, d.canny_lo); c["canny_hi"] = _sb(0, 500, d.canny_hi)
        adv.addWidget(_two(_row("Canny blur", c["canny_blur"]), _row("Canny low", c["canny_lo"])))
        c["canny_min_size"] = _sb(0, 500, d.canny_min_size)
        adv.addWidget(_two(_row("Canny high", c["canny_hi"]), _row("Canny min size", c["canny_min_size"])))
        c["canny_erode"] = _sb(0, 20, d.canny_erode); c["canny_dilate"] = _sb(0, 20, d.canny_dilate)
        adv.addWidget(_two(_row("Canny erode", c["canny_erode"]), _row("Canny dilate", c["canny_dilate"])))
        # --- otsu_edge ---
        adv.addWidget(ParamLabel("OTSU-EDGE"))
        c["otsu_edge_blur"] = _sb(0, 15, d.otsu_edge_blur); c["otsu_edge_offset"] = _sb(-100, 100, d.otsu_edge_offset)
        adv.addWidget(_two(_row("OtsuEdge blur", c["otsu_edge_blur"]), _row("OtsuEdge offset", c["otsu_edge_offset"])))
        c["otsu_edge_min_size"] = _sb(0, 500, d.otsu_edge_min_size)
        c["otsu_edge_erode"] = _sb(0, 20, d.otsu_edge_erode); c["otsu_edge_dilate"] = _sb(0, 20, d.otsu_edge_dilate)
        adv.addWidget(_row("OtsuEdge min size", c["otsu_edge_min_size"]))
        adv.addWidget(_two(_row("OtsuEdge erode", c["otsu_edge_erode"]), _row("OtsuEdge dilate", c["otsu_edge_dilate"])))
        # --- slic ---
        adv.addWidget(ParamLabel("SLIC"))
        c["slic_n"] = _sb(2, 5000, d.slic_n); c["slic_compact"] = _sb(1, 100, d.slic_compact); c["slic_sigma"] = _sb(0, 15, d.slic_sigma)
        adv.addWidget(_two(_row("SLIC N", c["slic_n"]), _row("SLIC compact", c["slic_compact"])))
        adv.addWidget(_row("SLIC sigma", c["slic_sigma"]))
        # --- phase otsu ---
        adv.addWidget(ParamLabel("PHASE · OTSU"))
        c["otsu_blur"] = _sb(0, 15, d.otsu_blur); c["otsu_offset"] = _sb(-100, 100, d.otsu_offset)
        adv.addWidget(_two(_row("Otsu blur", c["otsu_blur"]), _row("Otsu offset", c["otsu_offset"])))
        c["otsu_erode"] = _sb(0, 30, d.otsu_erode); c["otsu_dilate"] = _sb(0, 30, d.otsu_dilate)
        adv.addWidget(_two(_row("Otsu erode", c["otsu_erode"]), _row("Otsu dilate", c["otsu_dilate"])))
        # --- phase adaptive ---
        adv.addWidget(ParamLabel("PHASE · ADAPTIVE"))
        c["adapt_block"] = _sb(3, 501, d.adapt_block, 2); c["adapt_c"] = _sb(-50, 50, d.adapt_c)
        adv.addWidget(_two(_row("Adapt block", c["adapt_block"]), _row("Adapt C", c["adapt_c"])))
        c["adapt_erode"] = _sb(0, 30, d.adapt_erode); c["adapt_dilate"] = _sb(0, 30, d.adapt_dilate)
        adv.addWidget(_two(_row("Adapt erode", c["adapt_erode"]), _row("Adapt dilate", c["adapt_dilate"])))

    # ------------------------------------------------------------- STEP 3
    elif n == 3:
        c["multimask"] = SegGroup([("on", "on"), ("off", "off")], default="on" if d.multimask else "off")
        lay.addWidget(_row("Multimask (3 candidates)", c["multimask"]))
        c["mask_pick"] = SegGroup([("largest", "largest"), ("smallest", "smallest"), ("best", "best")], default=d.mask_pick)
        lay.addWidget(_row("Mask pick", c["mask_pick"]))
        c["batch_size"] = _sb(1, 256, d.batch_size)
        lay.addWidget(_row("Batch size", c["batch_size"]))
        model = QLineEdit("SAM2 (facebook/sam2-hiera-large)"); model.setEnabled(False)
        lay.addWidget(_row("Model", model))

    # ------------------------------------------------------------- STEP 4
    elif n == 4:
        c["min_score_g"] = _dsb(0, 1, 0.20, 0.05, 2); c["min_score_p"] = _dsb(0, 1, 0.10, 0.05, 2)
        lay.addWidget(_two(_row("Min score (grain)", c["min_score_g"]), _row("Min score (phase)", c["min_score_p"])))
        c["min_area_g"] = _sb(1, 5000, 50); c["min_area_p"] = _sb(1, 5000, 20)
        lay.addWidget(_two(_row("Min mask area (grain)", c["min_area_g"]), _row("Min mask area (phase)", c["min_area_p"])))
        c["max_mask_frac"] = _dsb(0.05, 1.0, d.max_mask_frac, 0.05, 2)
        lay.addWidget(_row("Max mask fraction", c["max_mask_frac"]))
        c["fill_grain_gaps"] = SegGroup([("on", "on"), ("off", "off")],
                                        default="on" if d.fill_grain_gaps else "off")
        lay.addWidget(_row("Fill grain gaps (no black background)", c["fill_grain_gaps"]))

        # --- grain-map post-processing (each an independent on/off toggle) ---
        lay.addWidget(ParamLabel("GRAIN POST-PROCESSING"))
        def _pp(key, label, dflt):
            c[key] = SegGroup([("on", "on"), ("off", "off")], default="on" if dflt else "off")
            lay.addWidget(_row(label, c[key]))
        _pp("pp_despeckle", "Despeckle (remove tiny grains)", d.pp_despeckle)
        _pp("pp_merge_fragments", "Merge tiny fragments into neighbour", d.pp_merge_fragments)
        _pp("pp_majority", "Majority-filter smoothing", d.pp_majority)
        _pp("pp_morph", "Morphological cleanup", d.pp_morph)

        adv = _adv(lay)
        adv.addWidget(ParamLabel("POST-PROCESSING PARAMS"))
        c["pp_min_grain_area"] = _sb(1, 5000, d.pp_min_grain_area)
        c["pp_majority_size"] = _sb(3, 15, d.pp_majority_size, 2)
        adv.addWidget(_two(_row("Despeckle/merge min area", c["pp_min_grain_area"]),
                           _row("Majority window (odd)", c["pp_majority_size"])))
        c["pp_morph_radius"] = _sb(1, 10, d.pp_morph_radius)
        adv.addWidget(_row("Morph cleanup radius", c["pp_morph_radius"]))
        adv.addWidget(ParamLabel("BASELINE PARAMS"))
        c["min_grain_area"] = _sb(1, 5000, d.min_grain_area)
        c["ws_footprint_base"] = _sb(2, 60, d.ws_footprint_base)
        adv.addWidget(_two(_row("Baseline min grain area", c["min_grain_area"]),
                           _row("Baseline WS footprint", c["ws_footprint_base"])))
        c["adapt_block_base"] = _sb(3, 501, d.adapt_block_base, 2); c["adapt_c_base"] = _sb(-50, 50, d.adapt_c_base)
        adv.addWidget(_two(_row("Baseline adapt block", c["adapt_block_base"]),
                           _row("Baseline adapt C", c["adapt_c_base"])))

    # ------------------------------------------------------------- STEP 5
    elif n == 5:
        c["fig_input"] = ChipButton("Input image", True)
        c["fig_grain"] = ChipButton("Grain result", True)
        c["fig_phase"] = ChipButton("Phase result", True)
        c["fig_overlay"] = ChipButton("Overlay", True)
        chips = QVBoxLayout(); chips.setSpacing(5)
        for w in (c["fig_input"], c["fig_grain"], c["fig_phase"], c["fig_overlay"]):
            chips.addWidget(w)
        cw = QWidget(); cw.setObjectName("RowCont"); cw.setLayout(chips)
        lay.addWidget(_row("Which image(s) to save", cw))
        hint = QLabel("Each ticked image is written as its OWN file — just the image, "
                      "no titles / axes / borders.")
        hint.setStyleSheet("color:#9aa7b8;font:11px Consolas;background:transparent;"); hint.setWordWrap(True)
        lay.addWidget(hint)
        c["save_format"] = SegGroup([("PNG", "PNG"), ("TIFF", "TIFF"), ("SVG", "SVG")], default=d.save_format)
        lay.addWidget(_row("Format", c["save_format"]))
        c["dpi"] = _sb(72, 600, d.fig_dpi); c["panel_h"] = _dsb(2, 15, d.panel_h, 0.5, 1)
        lay.addWidget(_two(_row("DPI", c["dpi"]), _row("Panel height (in)", c["panel_h"])))
        c["outfile"] = QLineEdit(d.outfile)
        lay.addWidget(_row("Output name (prefix)", c["outfile"]))

    lay.addStretch(1)
    return page, c


# ================================================================= RESULTS
def build_step_results(win, n):
    page = QWidget(); lay = QVBoxLayout(page); lay.setContentsMargins(26, 8, 26, 26); lay.setSpacing(14)
    refs = {}

    if n == 1:
        cards = QHBoxLayout(); cards.setSpacing(12)
        refs["pts"] = StatCard("Points loaded"); refs["shape"] = StatCard("Map shape"); refs["kam"] = StatCard("KAM mean")
        for c in (refs["pts"], refs["shape"], refs["kam"]):
            cards.addWidget(c)
        cards.addStretch(1); cw = QWidget(); cw.setLayout(cards); lay.addWidget(cw)
        refs["maps"] = FigurePane("Input maps", min_h=340); lay.addWidget(refs["maps"])

    elif n == 2:
        refs["grain"] = FigurePane("Seed preview — grain", min_h=280); lay.addWidget(refs["grain"])
        refs["phase"] = FigurePane("Seed preview — phase", min_h=280); lay.addWidget(refs["phase"])

    elif n == 3:
        cards = QHBoxLayout(); cards.setSpacing(12)
        refs["gm"] = StatCard("Grain masks"); refs["pm"] = StatCard("Phase masks"); refs["sc"] = StatCard("Score range", accent=True)
        for c in (refs["gm"], refs["pm"], refs["sc"]):
            cards.addWidget(c)
        cards.addStretch(1); cw = QWidget(); cw.setLayout(cards); lay.addWidget(cw)
        info = QLabel("SAM ran on the current seeds. Tune screening in Step 4 without re-running this.")
        info.setStyleSheet("color:#5c6775;font-size:12px;"); lay.addWidget(info)

    elif n == 4:
        cards = QHBoxLayout(); cards.setSpacing(12)
        refs["grains"] = StatCard("Grains", accent=True); refs["pfrac"] = StatCard("Phase frac"); refs["kept"] = StatCard("Masks kept")
        for c in (refs["grains"], refs["pfrac"], refs["kept"]):
            cards.addWidget(c)
        cards.addStretch(1); cw = QWidget(); cw.setLayout(cards); lay.addWidget(cw)
        refs["cmp_grain"] = FigurePane("Grain — MatSAM vs baselines", min_h=300); lay.addWidget(refs["cmp_grain"])
        refs["cmp_phase"] = FigurePane("Phase — MatSAM vs baselines", min_h=300); lay.addWidget(refs["cmp_phase"])
        refs["overlay"] = FigurePane("Overlay on IQ", min_h=300); lay.addWidget(refs["overlay"])

    elif n == 5:
        refs["preview"] = FigurePane("Save preview", min_h=340); lay.addWidget(refs["preview"])
        save = QPushButton("⬇  Save Image(s)"); save.setObjectName("RunBtn"); save.setMaximumWidth(220)
        save.clicked.connect(win.save_image); lay.addWidget(save)

    log = QPlainTextEdit(); log.setReadOnly(True); log.setObjectName("LogView")
    log.setMaximumBlockCount(3000); log.setMinimumHeight(110); log.setMaximumHeight(160)
    lay.addWidget(QLabel("Log")); lay.addWidget(log); refs["log"] = log
    lay.addStretch(1)
    return page, refs


# ================================================================= READ CONFIG
def read_all_controls(win) -> Config:
    c = win.step_ctrls
    s1, s2, s3, s4, s5 = c[0], c[1], c[2], c[3], c[4]
    cfg = Config()
    # Leave model_dir empty: the SAM runner resolves the app-local models/sam2
    # folder itself (matsam_engine.paths) and downloads it on first run if
    # missing. Setting it explicitly is only for pointing at a custom copy.
    cfg.model_dir = ""

    # step 1
    cfg.input_file = s1["ang"].text().strip(); cfg.ang_file = cfg.input_file
    cfg.task = s1["task"].value() or "both"
    cfg.input_channel = s1["input_channel"].value() or "iq"
    cfg.gpu_index = s1["gpu_index"].value()
    cfg.grid_ratio = s1["grid_ratio"].value()
    cfg.kam_vmax = s1["kam_vmax"].value()
    cfg.norm_lo = s1["norm_lo"].value(); cfg.norm_hi = s1["norm_hi"].value()
    if "crop_enabled" in s1:
        cfg.crop_enabled = s1["crop_enabled"].isChecked()
        cfg.crop_x = s1["crop_x"].value(); cfg.crop_y = s1["crop_y"].value()
        cfg.crop_w = s1["crop_w"].value(); cfg.crop_h = s1["crop_h"].value()

    # step 2 basic
    cfg.preseg_grain = s2["preseg_grain"].currentText()
    cfg.preseg_phase = s2["preseg_phase"].currentText()
    cfg.roi_grain = s2["roi_grain"].currentText(); cfg.roi_phase = s2["roi_phase"].currentText()
    cfg.grid_spacing = s2["grid_spacing"].value(); cfg.min_area = s2["min_area"].value()
    cfg.width_thresh = s2["width_thresh"].value()
    # step 2 advanced
    cfg.ws_blur = s2["ws_blur"].value(); cfg.ws_footprint = s2["ws_footprint"].value()
    cfg.ws_min_dist = s2["ws_min_dist"].value(); cfg.ws_compactness = s2["ws_compactness"].value()
    cfg.canny_blur = s2["canny_blur"].value(); cfg.canny_lo = s2["canny_lo"].value(); cfg.canny_hi = s2["canny_hi"].value()
    cfg.canny_min_size = s2["canny_min_size"].value(); cfg.canny_erode = s2["canny_erode"].value(); cfg.canny_dilate = s2["canny_dilate"].value()
    cfg.otsu_edge_blur = s2["otsu_edge_blur"].value(); cfg.otsu_edge_offset = s2["otsu_edge_offset"].value()
    cfg.otsu_edge_min_size = s2["otsu_edge_min_size"].value(); cfg.otsu_edge_erode = s2["otsu_edge_erode"].value(); cfg.otsu_edge_dilate = s2["otsu_edge_dilate"].value()
    cfg.slic_n = s2["slic_n"].value(); cfg.slic_compact = s2["slic_compact"].value(); cfg.slic_sigma = s2["slic_sigma"].value()
    cfg.otsu_blur = s2["otsu_blur"].value(); cfg.otsu_offset = s2["otsu_offset"].value()
    cfg.otsu_erode = s2["otsu_erode"].value(); cfg.otsu_dilate = s2["otsu_dilate"].value()
    cfg.adapt_block = s2["adapt_block"].value(); cfg.adapt_c = s2["adapt_c"].value()
    cfg.adapt_erode = s2["adapt_erode"].value(); cfg.adapt_dilate = s2["adapt_dilate"].value()

    # step 3
    cfg.multimask = (s3["multimask"].value() == "on")
    cfg.mask_pick = s3["mask_pick"].value() or "best"
    cfg.batch_size = s3["batch_size"].value()

    # step 4
    cfg.min_score = [s4["min_score_g"].value(), s4["min_score_p"].value()]
    cfg.min_mask_area = [s4["min_area_g"].value(), s4["min_area_p"].value()]
    cfg.max_mask_frac = s4["max_mask_frac"].value()
    cfg.fill_grain_gaps = (s4["fill_grain_gaps"].value() == "on")
    cfg.pp_despeckle = (s4["pp_despeckle"].value() == "on")
    cfg.pp_merge_fragments = (s4["pp_merge_fragments"].value() == "on")
    cfg.pp_majority = (s4["pp_majority"].value() == "on")
    cfg.pp_morph = (s4["pp_morph"].value() == "on")
    cfg.pp_min_grain_area = s4["pp_min_grain_area"].value()
    cfg.pp_majority_size = s4["pp_majority_size"].value()
    cfg.pp_morph_radius = s4["pp_morph_radius"].value()
    cfg.min_grain_area = s4["min_grain_area"].value(); cfg.ws_footprint_base = s4["ws_footprint_base"].value()
    cfg.adapt_block_base = s4["adapt_block_base"].value(); cfg.adapt_c_base = s4["adapt_c_base"].value()

    # step 5
    cfg.save_format = s5["save_format"].value() or "PNG"
    cfg.fig_dpi = s5["dpi"].value(); cfg.panel_h = s5["panel_h"].value()
    cfg.outfile = s5["outfile"].text().strip() or "matsam_result.png"
    return cfg
