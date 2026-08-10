"""Background worker — runs matsam stages off the GUI thread.

The 5 GUI stages map onto the engine:
  1 Load   -> load_maps
  2 Seeds  -> build_input + make_seeds (per task)          [cheap, re-run freely]
  3 SAM    -> SamRunner.run (per task)                     [EXPENSIVE, run once]
  4 Screen -> screen_all                                   [cheap, re-run freely]
  5 Save   -> handled on the GUI thread (fast)

The SamRunner (loaded model) is created once and kept, so Stage 3 re-runs
inference without re-loading the model, and Stage 4 never touches SAM.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from matsam_engine import (Config, load_maps, build_input, preseg, SamRunner,
                           screen)

STAGE_LOAD = 1
STAGE_SEEDS = 2
STAGE_SAM = 3
STAGE_SCREEN = 4
STAGE_SAVE = 5


class MatsamWorker(QObject):
    log = Signal(str)
    progress = Signal(int)
    stage_done = Signal(int, object)     # (stage, payload dict)
    finished = Signal(int)               # last stage completed
    failed = Signal(str)

    def __init__(self, cfg: Config, stage: int, state: dict, runner=None):
        super().__init__()
        self.cfg = cfg
        self.stage = stage
        self.state = state          # accumulates md / seeds / sam_out / result
        self.runner = runner        # persistent SamRunner (loaded model)

    def run(self):
        try:
            emit = lambda m="": self.log.emit(str(m))
            cfg = self.cfg; st = self.state
            tasks = ["grain", "phase"] if cfg.task == "both" else [cfg.task]

            if self.stage == STAGE_LOAD:
                emit("[1/5] Loading .ang and derived maps ...")
                st["md"] = load_maps(cfg, log=emit)
                self.stage_done.emit(STAGE_LOAD, {"md": st["md"]})

            elif self.stage == STAGE_SEEDS:
                emit("[2/5] Pre-segmentation + seed points ...")
                md = st["md"]
                seeds = {}
                for t in tasks:
                    seeds[t] = preseg.make_seeds(cfg, md, build_input(cfg, md, t), t, log=emit)
                st["seeds"] = seeds
                st["sam_out"] = None       # seeds changed -> SAM invalidated
                self.stage_done.emit(STAGE_SEEDS, {"seeds": seeds})

            elif self.stage == STAGE_SAM:
                emit("[3/5] Running SAM (expensive) ...")
                if self.runner is None:
                    self.runner = SamRunner(cfg, log=emit)
                md = st["md"]; seeds = st["seeds"]
                sam_out = {}
                ntask = len(seeds)
                for k, (t, S) in enumerate(seeds.items()):
                    def prog(p, base=int(100 * k / ntask), span=int(100 / ntask)):
                        self.progress.emit(base + p * span // 100)
                    sam_out[t] = self.runner.run(S, log=emit, progress=prog)
                st["sam_out"] = sam_out
                self.progress.emit(100)
                self.stage_done.emit(STAGE_SAM, {"sam_out": sam_out, "runner": self.runner})

            elif self.stage == STAGE_SCREEN:
                emit("[4/5] Screening masks ...")
                result = screen.screen_all(cfg, st["md"], st["seeds"], st["sam_out"], log=emit)
                st["result"] = result
                self.stage_done.emit(STAGE_SCREEN, {"result": result})

            emit(""); emit("Done.")
            self.finished.emit(self.stage)
        except Exception:
            import traceback
            self.failed.emit(traceback.format_exc())
