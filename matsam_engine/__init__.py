"""MatSAM engine — grain + phase segmentation.

Pure-compute layer (no GUI). Pipeline:
  load_maps -> build_input -> make_seeds -> SamRunner.run -> screen_all -> figures.
"""
from .config import Config, per_task
from .loader import MapData, load_maps, build_input, rgb_for_sam
from . import preseg
from .sam import SamRunner
from . import screen
from . import plotting
from . import saveimg

__all__ = ["Config", "per_task", "MapData", "load_maps", "build_input",
           "rgb_for_sam", "preseg", "SamRunner", "screen", "plotting", "saveimg"]
