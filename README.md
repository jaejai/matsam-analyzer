# MatSAM — standalone app

Desktop GUI for SAM2-based grain and phase segmentation of EBSD scans: load a
scan (`.ang`, `.osc`, `.ctf`, or h5ebsd), pre-segment + seed points, run **SAM2**
(ungated, Apache-2.0) once, screen the masks into grain / phase results, and
**save the result image** (PNG/TIFF/SVG).

## Layout

```
standalone_matsam/
├── app.py                  # PySide6 GUI (5-step pipeline, gating, save-image)
├── worker.py               # background QThread — staged; SAM model reused
├── matsam_engine/          # pure-compute layer (no GUI)
│   ├── config.py           # Config dataclass (all parameters)
│   ├── ebsd_read.py        # multi-format reader (.ang/.osc/.ctf/h5ebsd)
│   ├── loader.py           # load scan, IQ/CI/KAM maps, build model input
│   ├── preseg.py           # pre-seg, seed finders, baselines, make_seeds
│   ├── sam.py              # load SAM2, run inference, mask pick
│   ├── screen.py           # screen_grain / screen_phase
│   ├── plotting.py         # figures
│   ├── paths.py            # SAM2 model location / download
│   └── saveimg.py          # save figure(s) to image
└── ui/                     # theme, widgets, steps (shared UI framework)
```

The SAM2 weights live in `../models/sam2` (not bundled here). SAM2 is
`facebook/sam2-hiera-large` (Apache-2.0, ungated — no HuggingFace token).

## The 5-step flow (tune-cheap / run-once / re-tune-cheap)

1. **Load** — scan → IQ/CI/KAM maps.
2. **Pre-seg & Seeds** — rule-based pre-seg + ROI/grid prompt points. *Cheap; re-run freely.*
3. **Run SAM** — SAM2 inference (**expensive; runs once**). Locked until seeds exist.
4. **Screen** — masks → grain/phase result. *Cheap; re-tune without re-running SAM.*
5. **Save Image** — export the chosen figure(s).

**Gating:** changing a Step-2 seeding param invalidates the SAM run (Step 3 must
re-run); Step 4 needs Step 3; Step 5 needs Step 4. The loaded SAM model is kept
in memory, so re-running SAM does not re-load it, and screening never touches SAM.

## Install & run (end user, no Python knowledge needed)

1. Download / clone this folder.
2. Double-click **`install.bat`** (first time only). It downloads `pixi` and
   builds the environment from **conda-forge** (a few GB: PyTorch + CUDA).
3. Double-click **`launch.bat`** to start the GUI.

For development, run `python app.py` inside the environment `install.bat` builds.

**GPU or CPU — automatic.** `install.bat` runs `nvidia-smi`: if an NVIDIA GPU is
present it installs the **GPU** environment (CUDA PyTorch); otherwise it installs
the **CPU** environment (works on any machine, just slower). The choice is saved
to `.matsam-env` and `launch.bat` runs the matching one.

**No CUDA toolkit needed.** conda-forge bundles the full CUDA runtime + **cuDNN**
inside the GPU environment, so the user needs only an NVIDIA GPU and a reasonably
recent driver (CUDA-12-capable, roughly R525+ / late-2022). They never install
CUDA or cuDNN themselves, and there's no CUDA/cuDNN version-mismatch to manage —
the bundled runtime is matched to the bundled PyTorch.

**SAM2 model — automatic.** On the first launch the app looks for the model in
`models/sam2` next to the app. If it's there, it's used as-is (nothing is
downloaded). If it's missing, the app downloads `facebook/sam2-hiera-large`
(~0.9 GB, Apache-2.0, ungated — no HuggingFace token) into that folder. On a
network that blocks huggingface.co (corporate SSL proxy), the download fails
with a clear message telling the user to drop the model files into `models/sam2`
manually — after which it's found and reused. See `matsam_engine/paths.py`.

## Dependencies

PyTorch (CUDA), transformers, orix, scikit-image, opencv, **PySide6**. GPU
strongly recommended; falls back to CPU (much slower). All are fetched into a
private conda-forge environment by `install.bat`.

## Packaging (pixi)

```
pixi.toml      # conda-forge-only env (pytorch-gpu, transformers, pyside6, ...)
pixi.lock      # pinned + hashed resolve (win-64 + linux-64)
install.bat    # first-run: fetch pixi, build env
get_pixi.ps1   # downloads the pixi binary
launch.bat     # run the app inside the pixi env
```

`models/` and `.pixi*` are git-ignored, so the repo stays small (code only). The
SAM2 weights and the multi-GB env are fetched on the user's machine.

## License

- **SAM2** model (`facebook/sam2-hiera-large`): **Apache-2.0**, ungated — freely
  redistributable, no token. Loaded from `model.safetensors` (safe, non-pickle).
- **orix** is GPL v3 → the distributed application is **GPL v3** (see `LICENSE`).
- **PySide6** is LGPL v3 (dynamically linked via conda — compliant).
- PyTorch / transformers / numpy / scipy / scikit-image / Pillow = BSD / Apache / MIT.
- **opencv** comes from **conda-forge** (Apache-2.0 build, no GPL FFmpeg codecs).
- **pixi** is BSD-3 (prefix.dev); conda-forge only.
