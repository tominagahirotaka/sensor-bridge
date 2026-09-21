"""mylib.plot_utils: plot.py's data/analysis/plotting toolkit.

Split by responsibility into submodules (common/reading/filters/wavelet/
plotting/smoothing_gui/export); this package re-exports every public name
so existing callers (`import mylib.plot_utils as pltutils`, `pltutils.X`,
`from mylib.plot_utils import X`) keep working unchanged.
"""

from mylib.plot_utils.common import (COLORS, TimedPlotWidget, TimedViewBox,
                                     add_right_axis, bg_colors,
                                     colorbrewer_set1, create_labeled_slider,
                                     create_shift_input, cud_colors,
                                     decimate_fixed, decimate_for_range,
                                     find_nearest, font_family_name,
                                     init_pg, make_style, make_title_span,
                                     mk_checkbox, mk_image, mk_image0,
                                     mk_label, mk_plot, mk_radiobuttons,
                                     mouseMoved, mouseMovedImage, os_name,
                                     plot_additional_lines, plot_cpt_lines,
                                     set_axis_label, set_bg_color,
                                     style_dict, symbol_colors, tableau10,
                                     v_line)
from mylib.plot_utils.reading import PlotData, PlotImageData, ReadData
from mylib.plot_utils.filters import (SignalFilter, apply_default_filters,
                                      apply_filters, calc_cumsum, calc_ma,
                                      do_ma, resolve_filter_params)
from mylib.plot_utils.wavelet import (WaveletParams, calc_wavelet,
                                      compute_power_spectrum,
                                      compute_time_varying_freq_amp,
                                      do_compute_time_varying_freq_amp,
                                      do_power_spectrum, do_wavelet_transform,
                                      pair_peaks_valleys)
from mylib.plot_utils.plotting import (CrossHairManager, InitPlots,
                                       RegionManager, add_timeseries,
                                       auto_bins, calc_derivatives,
                                       calc_peaks_and_valleys,
                                       find_peaks_in_timeseries,
                                       get_optimal_bins, plot_peaks,
                                       plot_right_axis, plot_scalogram,
                                       plot_timeinterval_histogram,
                                       plot_timeseries, shift_image)
from mylib.plot_utils.smoothing_gui import (SignalSmoothingWindow, TabWindow,
                                            WaveletParamWindow)
from mylib.plot_utils.export import save_header

__all__ = [
    'COLORS', 'TimedPlotWidget', 'TimedViewBox', 'add_right_axis', 'bg_colors',
    'colorbrewer_set1', 'create_labeled_slider', 'create_shift_input',
    'cud_colors', 'decimate_fixed', 'decimate_for_range', 'find_nearest',
    'font_family_name', 'init_pg', 'make_style', 'make_title_span',
    'mk_checkbox', 'mk_image', 'mk_image0', 'mk_label', 'mk_plot',
    'mk_radiobuttons', 'mouseMoved', 'mouseMovedImage', 'os_name',
    'plot_additional_lines',
    'plot_cpt_lines', 'set_axis_label', 'set_bg_color', 'style_dict',
    'symbol_colors', 'tableau10', 'v_line',
    'PlotData', 'PlotImageData', 'ReadData',
    'SignalFilter', 'apply_default_filters', 'apply_filters', 'calc_cumsum',
    'calc_ma', 'do_ma', 'resolve_filter_params',
    'WaveletParams', 'calc_wavelet', 'compute_power_spectrum',
    'compute_time_varying_freq_amp', 'do_compute_time_varying_freq_amp',
    'do_power_spectrum', 'do_wavelet_transform', 'pair_peaks_valleys',
    'CrossHairManager', 'InitPlots', 'RegionManager', 'add_timeseries',
    'auto_bins', 'calc_derivatives', 'calc_peaks_and_valleys',
    'find_peaks_in_timeseries', 'get_optimal_bins', 'plot_peaks',
    'plot_right_axis', 'plot_scalogram', 'plot_timeinterval_histogram',
    'plot_timeseries', 'shift_image',
    'SignalSmoothingWindow', 'TabWindow', 'WaveletParamWindow',
    'save_header',
]
