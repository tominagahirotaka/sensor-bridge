"""Shared constants and low-level pyqtgraph/Qt widget-building helpers used
across the mylib.plot_utils package (color palettes, small pg.PlotItem/Qt
widget factories, mouse-move/crosshair label helpers, generic decimation)."""

import time
import platform

import numpy as np
import seaborn as sns
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (QButtonGroup, QCheckBox, QHBoxLayout, QLabel,
                             QLineEdit, QRadioButton, QSlider, QVBoxLayout,
                             QWidget)

from mylib.i18n import t as tr

pg.setConfigOptions(antialias=False)

font_family_name = {
    'Windows': 'Yu Gothic',
    'Linux': 'IPAexGothic',
    'Darwin': 'Hiragino Maru Gothic Pro'}

tableau10 = [
    '#1f77b4',  # Blue
    '#ff7f0e',  # Orange
    '#2ca02c',  # Green
    '#d62728',  # Red
    '#9467bd',  # Purple
    '#8c564b',  # Brown
    '#e377c2',  # Pink
    '#7f7f7f',  # Gray
    '#bcbd22',  # Olive
    '#17becf'   # Cyan
]
cud_colors = [
    '#E69F00',  # orange
    '#56B4E9',  # blue
    '#009E73',  # green
    '#F0E442',  # yellow
    '#0072B2',  # dark blue
    '#D55E00',  # red-orange
    '#CC79A7'   # pink
]
colorbrewer_set1 = [
    '#e41a1c',  # red
    '#377eb8',  # blue
    '#4daf4a',  # green
    '#984ea3',  # purple
    '#ff7f00',  # orange
    '#ffff33',  # yellow
    '#a65628',  # brown
    '#f781bf'   # pink
]

# COLORS = ['black', 'red', 'blue', 'magenta', 'green', 'indigo', 'cyan', 'maroon']
COLORS = colorbrewer_set1  # cud_colors #tableau10

# Define background colors
bg_colors = {
    "BN": "#FFC8C8",
    "DS": "#C8FFC8",
    "MA": "#C8C8FF",
    "LP": "#FFFFC8",
    "BP": "#CFCFC8",
    "TR": "#CFCFC8"}  # light red, light green, light blue, light yellow
symbol_colors = ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#D55E00', '#CC79A7']


def make_style(color='k', symbol='o', size=10, pen=None):
    return {
        'pen': pen,
        'symbol': symbol,
        'symbolBrush': color,
        'symbolPen': color,
        'symbolSize': size}


style_dict = {
    'circle': make_style(color='k', symbol='o'),
    'cross': make_style(color='k', symbol='x'),
    'square': make_style(color='k', symbol='s', size=14)
}

os_name = platform.system()
sns.set(font=font_family_name[os_name])

# Override ViewBox to measure paint time


class TimedViewBox(pg.ViewBox):
    def paint(self, p, opt, widget):
        t0 = time.perf_counter()
        super().paint(p, opt, widget)
        t1 = time.perf_counter()
        print(f"ViewBox paint: {(t1 - t0) * 1000:.1f}ms")

# Override PlotWidget


class TimedPlotWidget(pg.PlotWidget):
    def __init__(self, **kwargs):
        super().__init__(viewBox=TimedViewBox(), **kwargs)


# functions for pyqtgraph
#
# Initialize pyqtgraph
def init_pg(title):
    app = pg.mkQApp(title)
    win = pg.GraphicsLayoutWidget(show=True)
    win.setWindowTitle(title)
    win.setBackground('w')
    return app, win

# plot-related functions


def decimate_for_range(x, y, x_min, x_max, max_points=5000):
    """
    Extract and decimate only the data within the displayed range
    -> resolution automatically increases when zoomed in
    """
    # extract the data within the displayed range
    mask = (x >= x_min) & (x <= x_max)
    x_vis = x[mask]
    y_vis = y[mask]

    if len(x_vis) == 0:
        return x_vis, y_vis

    # use the original data as-is if the number of points in range is under max_points
    if len(x_vis) <= max_points:
        return x_vis, y_vis

    # decimate if there are too many
    step = len(x_vis) // max_points
    return x_vis[::step], y_vis[::step]


def decimate_fixed(x, y, max_points=5000):
    """Uniform decimation: simplest and fastest"""
    n = len(x)
    if n <= max_points:
        return x, y
    step = n // max_points
    return x[::step], y[::step]


def mouseMoved(evt, plots, vLine, hLine, xy):
    pos = evt
    x = xy.data[0][0]
    xlab, xunit = next(iter(xy.xlabel.values()))

    for p in plots.plts:
        if p.sceneBoundingRect().contains(pos):
            mousePoint = p.vb.mapSceneToView(pos)
            index = find_nearest(x, mousePoint.x())
            if index is not None and 0 <= index < len(x):
                label_text = make_title_span(
                    plots.title) + f'<span style="font-size: 12pt; color:green"> {xlab}={mousePoint.x():.5f}{xunit}'
                for (x, y), l, col in zip(xy.data, xy.labels, plots.color):
                    name, unit = next(iter(l.values()))
                    idx = find_nearest(x, mousePoint.x())
                    if 0 <= idx < len(y):
                        label_text += f", <span style='color:{col}'>{name}={
                            y[idx]:.2f}{unit}</span>"
                    else:
                        label_text += f", <span style='color:{col}'>{name}=---</span>"
                        # label_text += f", <span style='color:{col}'>{name}={y[index]:.2f}{unit}</span>"
                plots.label.setText(label_text)
            for v in vLine:
                v.setPos(mousePoint.x())
            for h in hLine:
                h.setPos(mousePoint.y())


def mouseMovedImage(evt, plots, vLine, hLine, xyz):
    pos = evt
    xlab, xunit = next(iter(xyz.xlabel.values()))
    # plot_scalogram() creates one Image per panel via
    # zip(plots.plts, xyz.data, xyz.labels), so plots.plts[k] corresponds to
    # xyz.data[k]/xyz.labels[k]. This used to hard-code k(=0), so hovering
    # over any panel only ever showed channel 0's label.
    for k, p in enumerate(plots.plts):
        if p.sceneBoundingRect().contains(pos):
            mouse_point = p.vb.mapSceneToView(pos)
            x, y = mouse_point.x(), mouse_point.y()
            image_data = xyz.data[k]
            time = image_data[0]
            ylab, yunit = next(iter(xyz.labels[k].values()))
            # get the image value (with bounds checking)
            if 0 <= x < time[-1] and 0 <= y < image_data[0].shape[0]:
                label_text = make_title_span(plots.title)
                label_text += f'<span style="font-size: 12pt"><span style="color:green"> {xlab}={
                    x:.2f}sec({
                    x /
                    60:.2f}min),</span> <span style="color: blue">{ylab}={
                    y:.2f}Hz({
                    y *
                    60:.1f}bpm)'
                plots.label.setText(label_text)
            for v in vLine:
                v.setPos(x)
            for h in hLine:
                h.setPos(y)


def make_title_span(str):
    return f'<span style="background-color: #333333; color: #e6e6e6; font-size: 13pt; padding: 3px 6px;">{str}:</span>'

##
# win.addItem-related functions
##
# make plot


def mk_plot(win, layout):
    plt = win.addPlot(row=layout[0], col=layout[1])
    plt.avgPen = pg.mkPen('#000000')
    plt.avgShadowPen = pg.mkPen('#8080DD', width=10)
#    plt.getViewBox().setBackgroundColor('#DDDDDD')  # gray
    plt.showGrid(x=True, y=True, alpha=0.8)
    plt.setAutoVisible(y=True)
    win.ci.layout.setRowStretchFactor(layout[0], layout[2])  # set StretchFactor
    return plt

# add plot


def add_right_axis(p1, label="Derivatives", color='g'):
    p2 = pg.ViewBox()
    p1.showAxis('right')
    p1.getAxis('right').linkToView(p2)
    p1.getAxis('right').setLabel(label, color=color)
    p1.scene().addItem(p2)
    p2.setXLink(p1)

    def updateViews():
        p2.setGeometry(p1.vb.sceneBoundingRect())
        p2.linkedViewChanged(p1.vb, p2.XAxis)

    updateViews()
    p1.vb.sigResized.connect(updateViews)
    return p2

# make label


def mk_label(win, layout, justify):
    label = pg.LabelItem(justify=justify)
    win.addItem(label, row=layout[0], col=layout[1])
    win.ci.layout.setRowStretchFactor(layout[0], layout[2])  # set StretchFactor
    return label

# make image


def mk_image0(plt, justify, values, ax_label):
    cmap = pg.colormap.getFromMatplotlib("jet")
    img = pg.ImageItem(justify=justify)
    plt.addItem(img)
    img.setColorMap(cmap)
    colorbar = plt.addColorBar(img, colorMap=cmap, values=values)
    set_axis_label(plt, ax_label)              # axis label
    return img, colorbar

# make image


def mk_image(win, layout, justify, values, ax_label):
    p = win.addPlot(row=layout[0], col=layout[1])
    # Set a custom color map
    # colors = [(0, 0, 0), (45, 5, 61),(84, 42, 55),(150, 87, 60),(208, 171, 141),(255, 255, 255)]
    # cmap = pg.ColorMap(pos=np.linspace(0.0, 1.0, 6), color=colors)
    # cmap='plasma' #viridis, plasma, magma, inferno, cividis[rf.
    # site-packages/pyqtgraph/colors/maps/]
    cmap = pg.colormap.getFromMatplotlib("jet")
    img = pg.ImageItem(justify=justify)
    p.addItem(img)
    img.setColorMap(cmap)
    p.addColorBar(img, colorMap=cmap, values=values)
    set_axis_label(p, ax_label)              # axis label
#    p.setLabel("bottom", ax_label[0])  # set the x-axis label
#    p.setLabel("left", ax_label[1])   # set the y-axis label
    win.ci.layout.setRowStretchFactor(layout[0], layout[2])  # set StretchFactor
    return p, img


# set axis label  (ex) ax_label = {'bottom': ('Time', 'sec'), 'left': ('Amplitude', 'V')}

def set_axis_label(p, ax_label):
    if ax_label:
        for axis, (label, unit) in ax_label.items():
            p.setLabel(axis, label, units=unit)

# plot vertical lines at Checkpoint positions


def plot_cpt_lines(plts, cpt_list, offset):
    lines = []
    for x in cpt_list:
        for p in plts:
            ln = v_line(x - offset, 'magenta')
            p.addItem(ln)
            lines.append((p, ln))
    return lines

# plot vertical lines at LT, PRE11-PRE13


def plot_additional_lines(plts, vline_dict):
    lines = []
    if vline_dict is not None:
        print(f'{vline_dict=}')
        for lab, x in vline_dict.items():
            if x is None or np.isnan(x):
                continue
            col = 'red' if lab == 'LT' else 'yellow'
            for p in plts:
                ln = v_line(x, col)
                p.addItem(ln)
                lines.append((p, ln))
    return lines


def v_line(pos, col):
    return pg.InfiniteLine(pos=pos, angle=90, pen=pg.mkPen(color=col, width=4))

# make checkbox
#  (e.g. choosing whether to show/hide a plot)
#  return: a list of checkboxes and labels


def mk_checkbox(labels, func, isChecked=True):
    checkboxes_layout = QHBoxLayout()
    checkboxes = []
    for lab in labels:
        checkbox_layout = QVBoxLayout()
        checkbox = QCheckBox("")
        checkbox.setChecked(isChecked)                              # checked by default
        checkbox_layout.addWidget(QLabel(f"{lab}"))
        checkbox_layout.addWidget(checkbox)
        checkbox.stateChanged.connect(func)
        checkboxes.append((lab, checkbox))
        checkboxes_layout.addLayout(checkbox_layout)
    return checkboxes_layout, checkboxes


# make radiobutton
# (e.g. shifting the initial time in a list of checkpoints; `sel` is the initially selected value)

def mk_radiobuttons(num, sel, func):
    radiobuttons_layout = QHBoxLayout()
    button_group = QButtonGroup()
    button_group.setExclusive(True)  # set the radio buttons to exclusive-selection mode
    for lab in range(num):
        radiobutton_layout = QVBoxLayout()
        label = QLabel(f"{lab}")
        radiobutton = QRadioButton("")
        radiobutton_layout.addWidget(label)
        radiobutton_layout.addWidget(radiobutton)
        if lab == sel:
            radiobutton.setChecked(True)  # select the first button
        button_group.addButton(radiobutton, id=lab)
        radiobutton.toggled.connect(func)  # connect the action for when a radio button is selected
        radiobuttons_layout.addLayout(radiobutton_layout)
    return radiobuttons_layout, button_group


def create_shift_input(
        label_text="Shift time(sec)",
        placeholder=None,
        max_length=10,
        tooltip=None):
    """
    Return a labeled layout for the Shift input.

    Returns:
        QWidget: a vertical layout widget containing the label and QLineEdit
        QLineEdit: the input field (used by the caller to read the value)
    """
    # Default arguments are evaluated once, at import time, before --lang is
    # resolved, so the catalog lookup happens in the function body instead,
    # which is only called after --lang is settled (deferred via a None sentinel).
    if placeholder is None:
        placeholder = tr('pu.shift_placeholder')
    if tooltip is None:
        tooltip = tr('pu.shift_tooltip')
    container = QWidget()
    layout = QVBoxLayout(container)
    label = QLabel(label_text)
    label.setToolTip(tooltip)
    layout.addWidget(label)

    line_edit = QLineEdit()
    line_edit.setPlaceholderText(placeholder)
    line_edit.setValidator(QIntValidator())
    line_edit.setMaxLength(max_length)
    line_edit.setFixedWidth(line_edit.fontMetrics().width('9' * max_length))

    layout.addWidget(line_edit)
    return container, line_edit


def create_labeled_slider(
        title: str,
        minimum: int,
        maximum: int,
        initial: int,
        interval: int = 1,
        orientation=Qt.Horizontal):
    """
    Create a widget combining a slider and its label.
    Parameters:
        title (str): the label's title (what the slider is for)
        minimum (int): the slider's minimum value
        maximum (int): the slider's maximum value
        initial (int): the initial value
        interval (int): the tick interval
        orientation (Qt.Orientation): Qt.Horizontal or Qt.Vertical
    Returns:
        QWidget: the widget containing the slider and label
        QSlider: the slider object (accessible externally)
    """
    container = QWidget()
    layout = QVBoxLayout() if orientation == Qt.Horizontal else QVBoxLayout()

    label = QLabel(f"{title}: {initial}sec")
    slider = QSlider(orientation)
    slider.setRange(minimum, maximum)
    slider.setValue(initial)
    slider.setTickInterval(interval)
    slider.setTickPosition(QSlider.TicksBelow if orientation ==
                           Qt.Horizontal else QSlider.TicksLeft)

    # also update the label whenever the slider's value changes
    slider.valueChanged.connect(lambda value: label.setText(f"{title}: {value}sec"))

    layout.addWidget(label)
    layout.addWidget(slider)
    container.setLayout(layout)

    return container, slider


def set_bg_color(history):
    color = bg_colors[history[:2]]
    return f"<span style='background-color: {color};'> {history} </span>"


####

def find_nearest(array, value):
    """Binary search on a sorted array; returns the nearest index"""
    if array is None or len(array) == 0:
        return None
    idx = np.searchsorted(array, value)
    # bounds check
    if idx == 0:
        return 0
    if idx >= len(array):
        return len(array) - 1
    # whether value is closer to array[idx-1] or array[idx]
    if abs(array[idx - 1] - value) <= abs(array[idx] - value):
        return idx - 1
    return idx
