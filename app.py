"""MatSAM Analyzer — standalone desktop GUI.

5-stage pipeline matching the approved mockup:
  1 Load  2 Pre-seg & Seeds  3 Run SAM  4 Screen  5 Save Image
with strict gating: changing seeds (Step 2) invalidates the SAM run (Step 3);
Step 4 needs Step 3; Step 5 needs Step 4. SAM runs once and is reused across
screening re-tunes. Save exports the result figure(s) as an image (no PowerPoint).

Run:  python app.py   (needs the EBSD_SAM3 env: torch + transformers)
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (HERE, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
if "NUMBA_CACHE_DIR" not in os.environ:      # orix/numba first-run cache safety
    _c = os.path.join(tempfile.gettempdir(), "matsam_numba_cache")
    try:
        os.makedirs(_c, exist_ok=True); os.environ["NUMBA_CACHE_DIR"] = _c
    except OSError:
        os.environ["NUMBA_CACHE_DIR"] = tempfile.gettempdir()

import matplotlib
matplotlib.use("QtAgg")

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QStackedWidget, QProgressBar, QMessageBox,
    QFileDialog,
)

from matsam_engine import plotting, saveimg
from ui.theme import STYLESHEET
from ui.widgets import MetricCard, SectionLabel
from ui.steps import build_step_controls, build_step_results, read_all_controls
from worker import MatsamWorker, STAGE_LOAD, STAGE_SEEDS, STAGE_SAM, STAGE_SCREEN, STAGE_SAVE

APP_TITLE = "MatSAM Analyzer"
STEPS = [
    ("Load", ".ang -> maps", "Read the TSL .ang scan and build the IQ / CI / KAM maps."),
    ("Pre-seg & Seeds", "watershed . points",
     "Rule-based pre-segmentation and ROI + grid prompt points. Cheap - re-run freely while tuning until the seeds look right."),
    ("Run SAM", "SAM2 . expensive",
     "Run SAM2 once on the seed points (the expensive step). Locked until seeds are built; changing seeds invalidates this."),
    ("Screen", "filter masks",
     "Turn raw masks into the final grain / phase result. Cheap - re-run freely without re-running SAM."),
    ("Save Image", "PNG / TIFF / SVG", "Export the result figure(s) as an image file."),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1480, 920); self.setMinimumSize(1180, 720)
        self.setStyleSheet(STYLESHEET)

        self.cfg = None
        self.state = {"md": None, "seeds": None, "sam_out": None, "result": None}
        self.runner = None            # persistent loaded SAM model
        self.step = 1
        self.sam_stale = False        # seeds changed since SAM last ran
        self._thread = None; self._worker = None

        self._build_ui()
        self.goto_step(1)

    # ===================================================================== UI
    def _build_ui(self):
        central = QWidget(); root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._header())
        body = QWidget(); bl = QHBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)
        bl.addWidget(self._sidebar()); bl.addWidget(self._main(), 1)
        root.addWidget(body, 1); self.setCentralWidget(central)

    def _header(self):
        h = QFrame(); h.setObjectName("Header"); h.setFixedHeight(58)
        lay = QHBoxLayout(h); lay.setContentsMargins(20, 0, 18, 0); lay.setSpacing(16)
        logo = QLabel("MatSAM Analyzer"); logo.setObjectName("Logo")
        sub = QLabel("Grain + Phase Segmentation"); sub.setObjectName("LogoSub")
        lb = QVBoxLayout(); lb.setSpacing(0); lb.addWidget(logo); lb.addWidget(sub)
        lw = QWidget(); lw.setLayout(lb); lay.addWidget(lw)
        self.file_chip = QLabel("no file loaded"); self.file_chip.setObjectName("FileChip")
        lay.addWidget(self.file_chip); lay.addStretch(1)
        self.m_masks = MetricCard("Masks", "-")
        self.m_grains = MetricCard("Grains", "-")
        self.m_phase = MetricCard("Phase", "-")
        self.m_model = MetricCard("Model", "SAM2", accent=True)
        for m in (self.m_masks, self.m_grains, self.m_phase, self.m_model):
            lay.addWidget(m)
        return h

    def _sidebar(self):
        side = QFrame(); side.setObjectName("Sidebar"); side.setFixedWidth(384)
        lay = QVBoxLayout(side); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        nav = QWidget(); nav.setObjectName("Nav"); nl = QVBoxLayout(nav)
        nl.setContentsMargins(12, 14, 12, 10); nl.setSpacing(2)
        nl.addWidget(SectionLabel("Pipeline"))
        self.nav_btns = []
        for i, (title, sub, _d) in enumerate(STEPS, start=1):
            b = QPushButton(); b.setObjectName("NavBtn"); b.setCheckable(True)
            b.setText(f"  {i}   {title}\n      {sub}")
            b.clicked.connect(lambda _=False, n=i: self.goto_step(n))
            self.nav_btns.append(b); nl.addWidget(b)
        lay.addWidget(nav)

        self.param_title = SectionLabel("Parameters . Load")
        host = QWidget(); host.setObjectName("ParamHost")
        hl = QVBoxLayout(host); hl.setContentsMargins(16, 12, 16, 6); hl.setSpacing(0)
        hl.addWidget(self.param_title)
        self.param_stack = QStackedWidget(); self.param_stack.setObjectName("ParamStack")
        self.step_ctrls = []
        for n in range(1, 6):
            page, ctrls = build_step_controls(self, n)
            self.step_ctrls.append(ctrls); self.param_stack.addWidget(page)
        hl.addWidget(self.param_stack); hl.addStretch(1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setObjectName("ParamScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # fit width; scroll vertically only
        scroll.setWidget(host); scroll.setFrameShape(QFrame.NoFrame); lay.addWidget(scroll, 1)

        foot = QFrame(); foot.setObjectName("RunFooter"); fl = QVBoxLayout(foot)
        fl.setContentsMargins(16, 13, 16, 16); fl.setSpacing(8)
        self.prog = QProgressBar(); self.prog.setObjectName("RunProg"); self.prog.setRange(0, 100)
        self.prog.setVisible(False); fl.addWidget(self.prog)
        self.run_btn = QPushButton("Run . Load"); self.run_btn.setObjectName("RunBtn")
        self.run_btn.clicked.connect(self.run_current); fl.addWidget(self.run_btn)
        self.run_note = QLabel(""); self.run_note.setObjectName("StageCount"); self.run_note.setAlignment(Qt.AlignCenter)
        fl.addWidget(self.run_note); lay.addWidget(foot)
        return side

    def _main(self):
        main = QFrame(); main.setObjectName("Main")
        lay = QVBoxLayout(main); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        head = QWidget(); hl = QVBoxLayout(head); hl.setContentsMargins(26, 22, 26, 8); hl.setSpacing(2)
        self.kicker = QLabel("STAGE 1 / 5"); self.kicker.setObjectName("Kicker")
        self.title = QLabel(STEPS[0][0]); self.title.setObjectName("StageTitle")
        self.desc = QLabel(STEPS[0][2]); self.desc.setObjectName("StageDesc"); self.desc.setWordWrap(True)
        hl.addWidget(self.kicker); hl.addWidget(self.title); hl.addWidget(self.desc); lay.addWidget(head)

        self.result_stack = QStackedWidget()
        self.step_results = []; self.result_pages = []
        for n in range(1, 6):
            page, refs = build_step_results(self, n)
            self.step_results.append(refs); self.result_pages.append(page)
            self.result_stack.addWidget(page)
        # size the stack to the CURRENT page only (via _size_result_stack in
        # goto_step): current page = Preferred (drives height, scrolls if tall),
        # every other page = Ignored (contributes 0). Without this the stack
        # inherits the TALLEST page's height, so a short page (Step 3) scrolls
        # needlessly, while all-Ignored would clip the tall page (Step 4).
        rs = QScrollArea(); rs.setWidgetResizable(True); rs.setFrameShape(QFrame.NoFrame)
        rs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rs.setWidget(self.result_stack); rs.setObjectName("ResultScroll"); lay.addWidget(rs, 1)

        foot = QWidget(); foot.setObjectName("MainFooter"); fl = QHBoxLayout(foot)
        fl.setContentsMargins(26, 12, 26, 16)
        self.back_btn = QPushButton("< Back"); self.back_btn.setObjectName("BackBtn")
        self.back_btn.clicked.connect(lambda: self.goto_step(max(1, self.step - 1)))
        self.count = QLabel("Stage 1 of 5"); self.count.setObjectName("StageCount")
        self.next_btn = QPushButton("Next >"); self.next_btn.setObjectName("NextBtn")
        self.next_btn.clicked.connect(lambda: self.goto_step(min(5, self.step + 1)))
        fl.addWidget(self.back_btn); fl.addStretch(1); fl.addWidget(self.count); fl.addStretch(1); fl.addWidget(self.next_btn)
        lay.addWidget(foot)
        return main

    # ================================================================= gating
    def _step_locked(self, n):
        if n == STAGE_SAM:
            return self.state["seeds"] is None
        if n == STAGE_SCREEN:
            return self.state["sam_out"] is None
        if n == STAGE_SAVE:
            return self.state["result"] is None
        return False

    def _size_result_stack(self, idx):
        """Make the result stack size to the CURRENT page only: current page
        drives height (scrolls if tall), others contribute nothing (so a short
        page never scrolls). See _main() for why."""
        from PySide6.QtWidgets import QSizePolicy as _SP
        for j, pg in enumerate(self.result_pages):
            sp = pg.sizePolicy()
            sp.setVerticalPolicy(_SP.Preferred if j == idx else _SP.Ignored)
            pg.setSizePolicy(sp)
        self.result_stack.adjustSize()

    def goto_step(self, n):
        if self._step_locked(n):
            QMessageBox.information(self, APP_TITLE, "Run the earlier steps first.")
            return
        self.step = n
        for i, b in enumerate(self.nav_btns, start=1):
            b.setChecked(i == n); b.setEnabled(not self._step_locked(i))
        self.param_stack.setCurrentIndex(n - 1)
        self.result_stack.setCurrentIndex(n - 1)
        self._size_result_stack(n - 1)
        self.param_title.setText("Parameters . " + STEPS[n - 1][0].split(" ")[0])
        self.kicker.setText(f"STAGE {n} / 5")
        self.title.setText(STEPS[n - 1][0]); self.desc.setText(STEPS[n - 1][2])
        self.count.setText(f"Stage {n} of 5"); self.back_btn.setEnabled(n > 1)
        self.next_btn.setText("Done" if n == 5 else "Next >")
        self._update_runbtn()

    def _update_runbtn(self):
        n = self.step
        if n == STAGE_SAM:
            if self.sam_stale:
                self.run_btn.setText("Re-run SAM (seeds changed)"); self.run_btn.setObjectName("RunBtn")
            else:
                self.run_btn.setText("Run . SAM2 (slow)")
        elif n == STAGE_SAVE:
            self.run_btn.setText("Save Image")
        else:
            self.run_btn.setText("Run . " + STEPS[n - 1][0])
        self.run_btn.setStyleSheet("")  # refresh
        dev = "GPU" if _cuda() else "CPU (slow)"
        self.run_note.setText(f"compute: {dev}")

    # ================================================================= run
    def run_current(self):
        n = self.step
        if n == STAGE_SAVE:
            self.save_image(); return
        cfg = read_all_controls(self)
        if not cfg.ang_file or not os.path.isfile(cfg.ang_file):
            QMessageBox.warning(self, APP_TITLE, "Select a valid .ang file first."); return
        if n >= STAGE_SEEDS and self.state["md"] is None:
            QMessageBox.information(self, APP_TITLE, "Run Step 1 (Load) first."); return
        if n == STAGE_SCREEN and self.state["sam_out"] is None:
            QMessageBox.information(self, APP_TITLE, "Run Step 3 (SAM) first."); return
        self.cfg = cfg
        self._start(n)

    def _start(self, stage):
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(self, APP_TITLE, "A run is already in progress."); return
        self._busy(True, stage == STAGE_SAM)
        thread = QThread()
        worker = MatsamWorker(self.cfg, stage, self.state, runner=self.runner)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(self._log)
        worker.progress.connect(self.prog.setValue)
        worker.stage_done.connect(self.on_stage_done)
        worker.finished.connect(self.on_finished)
        worker.failed.connect(self.on_failed)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_thread)
        self._thread = thread; self._worker = worker
        thread.start()

    def _clear_thread(self):
        self._thread = None; self._worker = None

    def _busy(self, on, show_prog=False):
        self.run_btn.setEnabled(not on)
        for b in self.nav_btns:
            b.setEnabled(not on and not self._step_locked(self.nav_btns.index(b) + 1))
        self.prog.setVisible(on and show_prog)
        if not on:
            self.prog.setValue(0)

    def _log(self, msg):
        for refs in self.step_results:
            lv = refs.get("log")
            if lv is not None:
                lv.appendPlainText(msg)

    def on_stage_done(self, stage, payload):
        if "runner" in payload:
            self.runner = payload["runner"]
        if stage == STAGE_LOAD:
            # re-loading may change task/input_channel -> everything downstream is
            # stale; clear it so old seeds/results can't linger
            self.state["seeds"] = None; self.state["sam_out"] = None; self.state["result"] = None
            self.sam_stale = False
            self._clear_downstream_panes()
        if stage == STAGE_SEEDS:
            self.sam_stale = True       # new seeds invalidate old SAM
            self.state["sam_out"] = None; self.state["result"] = None
        self._refresh(stage)

    def _clear_downstream_panes(self):
        """Blank out seed / result / preview figure panes so a previous task's
        images never linger after Load re-runs."""
        import matplotlib.figure as _mf
        blank = _mf.Figure(figsize=(1, 1))
        for key in ("grain", "phase"):
            self.step_results[1][key].show_figure(_mf.Figure(figsize=(1, 1)))
        for key in ("cmp_grain", "cmp_phase", "overlay"):
            self.step_results[3][key].show_figure(_mf.Figure(figsize=(1, 1)))
        self.step_results[4]["preview"].show_figure(_mf.Figure(figsize=(1, 1)))

    def on_finished(self, stage):
        self._busy(False)
        if stage == STAGE_SAM:
            self.sam_stale = False
        # unlock downstream nav
        for i, b in enumerate(self.nav_btns, start=1):
            b.setEnabled(not self._step_locked(i))
        self._update_metrics(); self._update_runbtn()

    def on_failed(self, tb):
        self._busy(False)
        self._log("\n[ERROR]\n" + tb)
        QMessageBox.critical(self, APP_TITLE, "Failed:\n\n" + tb.strip().splitlines()[-1])

    # ================================================================= refresh
    def _refresh(self, stage):
        cfg = self.cfg; st = self.state
        r1, r2, r3, r4, r5 = (self.step_results[i] for i in range(5))
        try:
            if stage == STAGE_LOAD:
                md = st["md"]
                r1["maps"].set_builder(lambda: plotting.fig_input_maps(cfg, md))
                r1["maps"].show_figure(plotting.fig_input_maps(cfg, md))
                r1["pts"].set_value(f"{md.iq.size:,}")
                r1["shape"].set_value(f"{md.H} × {md.W}")
                import numpy as _np
                r1["kam"].set_value(f"{_np.degrees(md.kam_arr.mean()):.2f}°" if md.kam_arr is not None else "n/a")
            elif stage == STAGE_SEEDS:
                seeds = st["seeds"]
                # show only the panes for the current task; hide the other so a
                # stale seed image from a previous task doesn't linger
                r2["grain"].setVisible("grain" in seeds)
                r2["phase"].setVisible("phase" in seeds)
                if "grain" in seeds:
                    r2["grain"].set_builder(lambda: plotting.fig_seeds(cfg, seeds["grain"]))
                    r2["grain"].show_figure(plotting.fig_seeds(cfg, seeds["grain"]))
                if "phase" in seeds:
                    r2["phase"].set_builder(lambda: plotting.fig_seeds(cfg, seeds["phase"]))
                    r2["phase"].show_figure(plotting.fig_seeds(cfg, seeds["phase"]))
            elif stage == STAGE_SAM:
                so = st["sam_out"]
                gm = len(so.get("grain", {}).get("masks", [])) if "grain" in so else 0
                pm = len(so.get("phase", {}).get("masks", [])) if "phase" in so else 0
                r3["gm"].set_value(f"{gm}"); r3["pm"].set_value(f"{pm}")
                allsc = [s for o in so.values() for s in o["scores"]]
                r3["sc"].set_value(f"{min(allsc):.2f}–{max(allsc):.2f}" if allsc else "-")
            elif stage == STAGE_SCREEN:
                res = st["result"]; seeds = st["seeds"]
                has_g = "grain" in res; has_p = "phase" in res; has_both = has_g and has_p
                has_any = has_g or has_p
                # show only the panes relevant to the current task; the overlay
                # pane is shown for ANY task (grain-only, phase-only, or both).
                r4["cmp_grain"].setVisible(has_g)
                r4["cmp_phase"].setVisible(has_p)
                r4["overlay"].setVisible(has_any)
                # stat cards: grey out N/A ones
                r4["grains"].set_value(f"{int(res['grain'].max())}" if has_g else "-")
                r4["pfrac"].set_value(f"{100*res['phase'].mean():.1f}%" if has_p else "-")
                if has_g:
                    r4["cmp_grain"].set_builder(lambda: plotting.fig_compare(cfg, st["md"], seeds, res, "grain"))
                    r4["cmp_grain"].show_figure(plotting.fig_compare(cfg, st["md"], seeds, res, "grain"))
                if has_p:
                    r4["cmp_phase"].set_builder(lambda: plotting.fig_compare(cfg, st["md"], seeds, res, "phase"))
                    r4["cmp_phase"].show_figure(plotting.fig_compare(cfg, st["md"], seeds, res, "phase"))
                if has_any:
                    r4["overlay"].set_builder(lambda: plotting.fig_overlay(cfg, st["md"], seeds, res))
                    r4["overlay"].show_figure(plotting.fig_overlay(cfg, st["md"], seeds, res))
                # Step-5 preview: always the overlay (grain and/or phase over IQ)
                prev = lambda: plotting.fig_overlay(cfg, st["md"], seeds, res)
                r5["preview"].set_builder(prev); r5["preview"].show_figure(prev())
                # Step-5 save chips: overlay is available for ANY task now
                s5 = self.step_ctrls[4]
                for key, avail in (("fig_input", has_any),
                                   ("fig_grain", has_g), ("fig_phase", has_p),
                                   ("fig_overlay", has_any)):
                    s5[key].setEnabled(avail)
                    if not avail:
                        s5[key].setChecked(False)
        except Exception as e:
            self._log(f"[plot error stage {stage}] {e}")

    def _update_metrics(self):
        st = self.state
        if st["sam_out"]:
            n = sum(len(o["masks"]) for o in st["sam_out"].values())
            self.m_masks.set_value(f"{n:,}")
        if st["result"]:
            if "grain" in st["result"]:
                self.m_grains.set_value(f"{int(st['result']['grain'].max())}")
            if "phase" in st["result"]:
                self.m_phase.set_value(f"{100*st['result']['phase'].mean():.1f}%")

    # ================================================================= save
    def save_image(self):
        st = self.state
        if not st.get("result"):
            QMessageBox.information(self, APP_TITLE, "Run the analysis (through Step 4) first."); return
        cfg = read_all_controls(self); self.cfg = cfg
        s5 = self.step_ctrls[4]
        res = st["result"]

        has_g = "grain" in res; has_p = "phase" in res; has_both = has_g and has_p
        seeds = st["seeds"]; md = st["md"]

        # Build the list of (suffix, figure-builder) for every ticked+available
        # image. Each is a BARE single image: no titles, axes or borders.
        # "Input image" is saved once per available task (grain input = IQ,
        # phase input = composite), since they can differ.
        jobs = []
        if s5["fig_input"].isChecked():
            if has_g:
                jobs.append(("input_grain", lambda: plotting.bare_input(cfg, md, "grain")))
            if has_p:
                jobs.append(("input_phase", lambda: plotting.bare_input(cfg, md, "phase")))
        if s5["fig_grain"].isChecked() and has_g:
            jobs.append(("grain", lambda: plotting.bare_grain(cfg, res)))
        if s5["fig_phase"].isChecked() and has_p:
            jobs.append(("phase", lambda: plotting.bare_phase(cfg, res)))
        if s5["fig_overlay"].isChecked() and (has_g or has_p):
            jobs.append(("overlay", lambda: plotting.bare_overlay(cfg, md, seeds, res)))
        if not jobs:
            QMessageBox.information(self, APP_TITLE, "Tick at least one image to save."); return

        # ask for a base name; each image is written as its OWN file:
        #   <base>_grain.png, <base>_phase.png, <base>_overlay.png, <base>_input_*.png
        ext = cfg.save_format.lower().replace("tiff", "tif")
        default = os.path.join(ROOT, os.path.splitext(cfg.outfile)[0])
        base, _ = QFileDialog.getSaveFileName(
            self, "Save Image(s) — base name (each image -> its own file)",
            default, f"{cfg.save_format} (*.{ext})")
        if not base:
            return
        base = os.path.splitext(base)[0]   # strip any extension the user typed
        try:
            written = []
            for suffix, build in jobs:
                fig = build()
                out = f"{base}_{suffix}.{ext}"
                saveimg.save_figure(fig, out, cfg, log=self._log)
                written.append(os.path.basename(out))
            QMessageBox.information(self, APP_TITLE,
                                    "Saved " + str(len(written)) + " file(s):\n" + "\n".join(written))
        except Exception as e:
            import traceback
            self._log("\n[SAVE ERROR]\n" + traceback.format_exc())
            QMessageBox.critical(self, APP_TITLE, f"Save failed:\n{e}")


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    win = MainWindow(); win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
