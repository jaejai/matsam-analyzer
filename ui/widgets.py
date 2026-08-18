"""Reusable Qt widgets for the EBSD ODF Analyzer GUI."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup,
    QSizePolicy, QDialog, QSpinBox, QDoubleSpinBox, QAbstractSpinBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure


def _plusminus(spin):
    """Wrap a spinbox with big, clearly-visible [−] value [+] buttons.

    The native up/down arrows are hidden (they read as invisible on the dark
    sidebar); the flanking buttons step the value and are obvious to click.
    Returns a container QWidget holding the buttons + spinbox.
    """
    spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
    box = QWidget(); box.setObjectName("SpinRow")
    lay = QHBoxLayout(box); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
    minus = QPushButton("−"); plus = QPushButton("+")     # − and +
    for b in (minus, plus):
        b.setObjectName("SpinStep"); b.setFixedWidth(30)
        b.setFocusPolicy(Qt.NoFocus); b.setAutoRepeat(True)
    minus.clicked.connect(spin.stepDown)
    plus.clicked.connect(spin.stepUp)
    lay.addWidget(minus); lay.addWidget(spin, 1); lay.addWidget(plus)
    # expose the spinbox on the container so callers can read .value()
    box.spin = spin
    return box


class StepSpinBox(QSpinBox):
    """Integer spinbox with flanking +/- buttons. Use .row() to add to a layout;
    .value()/.setValue() proxy straight through to the spinbox itself."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._row = _plusminus(self)

    def row(self):
        return self._row


class StepDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._row = _plusminus(self)

    def row(self):
        return self._row


class PlotDialog(QDialog):
    """Large pop-up view of a plot, with matplotlib zoom/pan/save toolbar."""
    def __init__(self, fig_builder, title="Plot", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 760)
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 6, 6, 6)
        fig = fig_builder()
        try:
            fig.set_layout_engine("constrained")
        except Exception:
            pass
        self.canvas = FigureCanvas(fig)
        self.toolbar = NavigationToolbar(self.canvas, self)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas, 1)


def mono(lbl: QLabel) -> QLabel:
    f = lbl.font(); f.setFamily("Consolas"); lbl.setFont(f); return lbl


class SectionLabel(QLabel):
    def __init__(self, text):
        super().__init__(text.upper()); self.setObjectName("SectionLabel")


# Bright label color for the dark sidebar — set directly on the widget so it
# always applies, regardless of stylesheet ancestor-selector matching.
PARAM_LABEL_CSS = "color:#e3eaf3; font-size:11px; font-weight:700; background:transparent;"


class ParamLabel(QLabel):
    """A parameter caption guaranteed readable on the dark sidebar.
    Wraps long text so it never forces the sidebar column wider than its width."""
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet(PARAM_LABEL_CSS)
        self.setWordWrap(True)
        self.setMinimumWidth(0)


class MetricCard(QFrame):
    """Small header metric card (value + label)."""
    def __init__(self, label, value, accent=False):
        super().__init__()
        self.setObjectName("MetricCardAccent" if accent else "MetricCard")
        self.setMinimumWidth(92)   # enough room for "2.41 um" / "TEXTURE J"
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 5, 12, 5); lay.setSpacing(1)
        self.val = QLabel(value); self.val.setObjectName("MetricValueAccent" if accent else "MetricValue")
        self.val.setAlignment(Qt.AlignRight)
        self.lbl = QLabel(label.upper()); self.lbl.setObjectName("MetricLabel")
        self.lbl.setAlignment(Qt.AlignRight)
        lay.addWidget(self.val); lay.addWidget(self.lbl)

    def set_value(self, v):
        self.val.setText(str(v))


class StatCard(QFrame):
    """Larger result-pane stat card."""
    def __init__(self, label, value="-", accent=False):
        super().__init__()
        self.setObjectName("StatCardAccent" if accent else "StatCard")
        self.setMinimumWidth(124)
        lay = QVBoxLayout(self); lay.setContentsMargins(15, 12, 15, 12); lay.setSpacing(5)
        self.lbl = QLabel(label.upper()); self.lbl.setObjectName("StatLabel")
        self.val = QLabel(value); self.val.setObjectName("StatValueAccent" if accent else "StatValue")
        lay.addWidget(self.lbl); lay.addWidget(self.val)

    def set_value(self, v):
        self.val.setText(str(v))


class Card(QFrame):
    """White rounded card with optional title and a content layout."""
    def __init__(self, title=None, caption=None):
        super().__init__(); self.setObjectName("Card")
        self.v = QVBoxLayout(self); self.v.setContentsMargins(0, 0, 0, 0); self.v.setSpacing(0)
        if title is not None:
            head = QWidget(); hl = QHBoxLayout(head); hl.setContentsMargins(13, 9, 13, 9)
            t = QLabel(title); t.setObjectName("CardTitle"); hl.addWidget(t)
            if caption:
                hl.addStretch(1); c = QLabel(caption); c.setObjectName("CardCaption"); hl.addWidget(c)
            self.v.addWidget(head)
        self.body = QWidget(); self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(11, 4, 11, 11)
        self.v.addWidget(self.body)


class FigurePane(QFrame):
    """A titled card wrapping an embedded matplotlib canvas.

    Each new figure gets a FRESH FigureCanvas. Reassigning ``canvas.figure`` on
    an existing canvas does not rebind it cleanly and leaves the canvas drawing
    a stale buffer at the wrong size (renders as stripes / a thin sliver), so we
    replace the canvas widget every time instead.
    """
    def __init__(self, title="", caption=None, min_h=300):
        super().__init__(); self.setObjectName("Card")
        self._min_h = min_h
        self._title = title
        self._builder = None     # callable() -> Figure, for the zoom popup
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        if title:
            head = QWidget(); hl = QHBoxLayout(head); hl.setContentsMargins(13, 9, 13, 9)
            t = QLabel(title); t.setObjectName("CardTitle"); hl.addWidget(t)
            hl.addStretch(1)
            hint = QLabel("click to enlarge ⤢"); hint.setObjectName("CardCaption")
            hl.addWidget(hint)
            if caption:
                c = QLabel(caption); c.setObjectName("CardCaption"); hl.addWidget(c)
            v.addWidget(head)
        # canvas host: we swap the canvas inside this layout
        self._host = QWidget()
        self._host_l = QVBoxLayout(self._host)
        self._host_l.setContentsMargins(8, 8, 8, 8)
        v.addWidget(self._host)
        self.setCursor(Qt.PointingHandCursor)

        self.figure = Figure(figsize=(4, 4))
        self.canvas = None
        self._install_canvas(self.figure)

    # crop-selection support (set via enable_crop)
    _crop_cb = None
    _crop_selector = None

    def set_builder(self, builder):
        """Store the figure-builder so a click can re-render it large."""
        self._builder = builder

    def enable_crop(self, callback):
        """Turn this pane into a drag-to-crop surface.

        `callback(x0, y0, w, h)` (integer pixels on the displayed map) is called
        as the user drags a rectangle. While crop mode is on, clicking the pane
        does NOT open the enlarge popup (the drag would otherwise fight it).
        Call enable_crop(None) to turn it back off.
        """
        self._crop_cb = callback
        self._attach_selector()

    def _attach_selector(self):
        # (re)attach a RectangleSelector to the first axes of the current figure
        from matplotlib.widgets import RectangleSelector
        self._crop_selector = None
        if self._crop_cb is None or not self.figure.axes:
            return
        ax = self.figure.axes[0]

        def _on_select(epress, erelease):
            if epress.xdata is None or erelease.xdata is None:
                return
            x0, x1 = sorted((epress.xdata, erelease.xdata))
            y0, y1 = sorted((epress.ydata, erelease.ydata))
            x0i, y0i = int(round(x0)), int(round(y0))
            wi, hi = int(round(x1 - x0)), int(round(y1 - y0))
            if wi >= 2 and hi >= 2 and self._crop_cb:
                self._crop_cb(max(0, x0i), max(0, y0i), wi, hi)

        try:
            self._crop_selector = RectangleSelector(
                ax, _on_select, useblit=True, button=[1], minspanx=3, minspany=3,
                spancoords="data", interactive=True,
                props=dict(facecolor="none", edgecolor="#3B82F6", linewidth=1.6))
        except Exception:
            self._crop_selector = None

    def mouseDoubleClickEvent(self, event):
        if self._crop_cb is None:
            self._open_popup()

    def mousePressEvent(self, event):
        # single click enlarges — but not while crop-dragging is active
        if self._crop_cb is None:
            self._open_popup()

    def _open_popup(self):
        if self._builder is None:
            return
        dlg = PlotDialog(self._builder, title=self._title or "Plot", parent=self.window())
        dlg.show()

    def _install_canvas(self, fig: Figure):
        # remove the previous canvas widget entirely
        if self.canvas is not None:
            self._host_l.removeWidget(self.canvas)
            self.canvas.setParent(None)
            self.canvas.deleteLater()
        self.figure = fig
        self.canvas = FigureCanvas(fig)
        self.canvas.setMinimumHeight(self._min_h)
        # Cap the canvas width to the figure's own aspect at this height, so a
        # tall/narrow figure is NOT given a canvas far wider than it can fill
        # (which left big side gaps and pushed the panels apart). Height still
        # expands; width is bounded to the figure aspect + a little slack.
        try:
            fw, fh = fig.get_size_inches()
            aspect = float(fw) / float(fh) if fh else 1.0
            self.canvas.setMaximumWidth(int(self._min_h * aspect * 1.15) + 40)
        except Exception:
            pass
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setStyleSheet("background:#ffffff;")
        # centre a width-capped canvas so a narrow figure sits in the middle of
        # the card rather than hugging the left edge.
        self._host_l.addWidget(self.canvas, alignment=Qt.AlignHCenter)

    def show_figure(self, fig: Figure):
        # constrained layout keeps colorbars/labels inside the axes box; a fresh
        # canvas then renders the whole figure scaled to the widget. A figure that
        # set _packed (tight custom layout, e.g. adjacent image panels) is left
        # as-is so its packing is not overridden.
        if not getattr(fig, "_packed", False):
            try:
                fig.set_layout_engine("constrained")
            except Exception:
                pass
        self._install_canvas(fig)
        self.canvas.draw_idle()
        # re-arm the crop selector on the new axes if crop mode is active
        if self._crop_cb is not None:
            self._attach_selector()


class SegGroup(QWidget):
    """Row of mutually-exclusive segmented buttons; .value() -> selected key."""
    def __init__(self, options, default=None):
        super().__init__()
        # allow the group to shrink below its natural width so 3+ buttons never
        # overflow a narrow sidebar column (they get clipped otherwise)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
        self.group = QButtonGroup(self); self.group.setExclusive(True)
        self._keys = {}
        for key, text in options:
            b = QPushButton(text); b.setObjectName("SegBtn"); b.setCheckable(True)
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            b.setMinimumWidth(0)
            self.group.addButton(b); lay.addWidget(b); self._keys[b] = key
            if key == default:
                b.setChecked(True)

    def value(self):
        b = self.group.checkedButton()
        return self._keys.get(b) if b else None


# convenience alias kept for app import symmetry
SegButton = SegGroup


class ChipButton(QPushButton):
    def __init__(self, text, checked=True):
        super().__init__(text); self.setObjectName("ChipBtn")
        self.setCheckable(True); self.setChecked(checked)
