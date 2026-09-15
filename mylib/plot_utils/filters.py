"""Signal-smoothing filter pipeline: SignalFilter (trim/downsample/moving
average/lowpass/bandnotch/bandpass) plus the apply_filters/apply_default_filters
helpers that drive it, and the standalone moving-average/cumsum PlotData ops."""

import numpy as np
import scipy.signal as signal

from mylib.i18n import t as tr
from mylib.plot_utils.reading import PlotData


# Compute the moving average
def do_ma(xy, mva_sec):
    t = xy.data[0][0]
    delta_t = (t[-1] - t[0]) / (len(t) - 1)
    print(f'{delta_t=}, {mva_sec=}')
    window = int(float(mva_sec) / delta_t)
    mv = PlotData()
    mv.xlabel = xy.xlabel
    mv.title = tr('pu.mavg_title', title=xy.title, sec=mva_sec)
    mv.subtitle = xy.subtitle
    print(mv.title)
    for dt, l in zip(xy.data, xy.labels):
        lab = {k: (v[0], '') for k, v in l.items()}
        t, y = calc_ma(dt, window)
        mv.add_series(t, y, label=lab)
    return mv

# Compute the cumulative sum


def calc_cumsum(xy):
    cm = PlotData()
    cm.xlabel = xy.xlabel
    cm.title = xy.title
    cm.subtitle = xy.subtitle
    for (t, y), l in zip(xy.data, xy.labels):
        lab = {k: (v[0], '') for k, v in l.items()}
        cm_y = np.cumsum(y)
        cm.add_series(t, cm_y, label=lab)
    return cm


def calc_ma(data, window):  # ignore the edges and use only the "exact" portion (mode='valid')
    t, y = data
    filtered_y = np.convolve(y, np.ones(window) / window, mode='valid')
    # filtered_y's length is len(y) - window + 1
    start = window // 2
    end = start + len(filtered_y)
    t_new = t[start:end]
    return (t_new, filtered_y)

# filter-related functions


def apply_filters(data, filter_history, cpt_lst=None):
    """
    Apply filters according to filter_history.
    cpt_lst: the list of checkpoints (optional)
    """
    if cpt_lst is None:
        cpt_lst = []
    resolved = resolve_filter_params(filter_history, cpt_lst)
    return SignalFilter(data).apply(resolved).data


def resolve_filter_params(history, cpt_lst):
    resolved = []
    for method, params in history:
        new_params = []
        for p in params:
            if isinstance(p, dict) and 'mark' in p:
                if len(cpt_lst) == 0:
                    print(tr('pu.warn_cpt_lst_empty'))
                    new_params.append(0.0)
                else:
                    cpt_idx = p['mark']
                    if cpt_idx >= len(cpt_lst):
                        print(tr('pu.warn_index_out_of_range', idx=cpt_idx))
                        new_params.append(cpt_lst[-1])
                    else:
                        new_params.append(cpt_lst[cpt_idx])
            else:
                new_params.append(p)
        resolved.append([method, new_params])
    return resolved


def apply_default_filters(data_list, default_filter, cpt_lst=None):
    """
    Parameters
    ----------
    data_list : list of (t, y) tuples
    default_filter : dict or list
    cpt_lst : the list of checkpoints (optional)

    Returns
    -------
    filter_history : dict  {idx: filter_history}
    data_list      : list  the data after filters are applied
    """
    if cpt_lst is None:
        cpt_lst = []
    num_data = len(data_list)

    if not default_filter:
        filter_history = {idx: [] for idx in range(num_data)}
    elif isinstance(default_filter, dict):
        filter_history = {int(key): val for key, val in default_filter.items()}
    elif isinstance(default_filter, list):
        filter_history = {idx: default_filter for idx in range(num_data)}
    else:
        print(tr('pu.warn_unsupported_filter_type', filter_type=type(default_filter)))
        filter_history = {idx: [] for idx in range(num_data)}

    for idx in range(num_data):
        if filter_history[idx]:
            data_list[idx] = apply_filters(data_list[idx], filter_history[idx], cpt_lst)

    return filter_history, data_list


class SignalFilter:
    """
    Class bundling the signal-smoothing filters together.
    Takes data = a (t, y) tuple, applies each filter, and returns the result.
    """

    METHOD_MAP = {
        'DS': 'downsample',
        'MA': 'moving_average',
        'LP': 'lowpass',
        'BN': 'bandnotch',
        'BP': 'bandpass',
        'TR': 'trim',
    }

    def __init__(self, data: tuple):
        """
        Parameters
        ----------
        data : a (t, y) tuple
        """
        self.t, self.y = data

    @property
    def data(self) -> tuple:
        return (self.t, self.y)

    @property
    def fs(self) -> float:
        """Current sampling frequency [Hz]"""
        return 1 / (self.t[1] - self.t[0])

    @property
    def nyq(self) -> float:
        """Nyquist frequency [Hz]"""
        return self.fs / 2

    # ------------------------------------------------------------------ #
    #  Individual filter methods (update self.t, self.y in-place and return self) #
    # ------------------------------------------------------------------ #

    def trim(self, t_min: float, t_max: float = None, reset_t0: bool = False) -> "SignalFilter":
        """
        Cut the time series to the given range [t_min, t_max]
        """
        if t_min is None:
            t_min = self.t[0]
        if t_max is None:
            t_max = self.t[-1]  # use the data's max value when None
        mask = (self.t >= t_min) & (self.t <= t_max)
        self.t = self.t[mask]
        self.y = self.y[mask]
        if reset_t0:
            self.t = self.t - self.t[0]  # offset so t_min's point becomes 0
        return self

    def downsample(self, new_fs: int, is_anti_alias: bool) -> "SignalFilter":
        downsample_factor = int(self.fs) // new_fs
        if is_anti_alias:
            cutoff = new_fs / 2
            normalized_cutoff = cutoff / self.nyq
            print(f'{self.fs=}, {normalized_cutoff=}, {cutoff=}, {self.nyq=}')
            b, a = signal.butter(4, normalized_cutoff, btype='low')
            y_proc = signal.filtfilt(b, a, self.y)
        else:
            y_proc = self.y
        print('Down sampling')
        self.t = self.t[::downsample_factor]
        self.y = y_proc[::downsample_factor]
        return self

    def moving_average(self, window: int) -> "SignalFilter":
        """Ignore the edges and use only the "exact" portion (mode='valid')"""
        filtered_y = np.convolve(self.y, np.ones(window) / window, mode='valid')
        start = window // 2
        end = start + len(filtered_y)
        self.t = self.t[start:end]
        self.y = filtered_y
        return self

    def lowpass(self, cutoff: float) -> "SignalFilter":
        norm_cutoff = cutoff / self.nyq
        if not (0 < norm_cutoff < 1):
            raise ValueError(tr('pu.cutoff_range_error', cutoff=cutoff, nyq=self.nyq))
        b, a = signal.butter(4, norm_cutoff, btype='low')
        self.y = signal.filtfilt(b, a, self.y)
        print('Lowpass filter')
        return self

    def bandnotch(self, f0: float, Q: float) -> "SignalFilter":
        w0 = f0 / self.nyq
        b, a = signal.iirnotch(w0, Q)
        self.y = signal.filtfilt(b, a, self.y)
        return self

    def bandpass(self, lowcut: float, highcut: float) -> "SignalFilter":
        low = lowcut / self.nyq
        high = highcut / self.nyq
        if not (0 < low < high < 1):
            raise ValueError(f"Invalid frequency range: {low=}, {high=}")
        baseline = np.mean(self.y)
        sos = signal.butter(4, [low, high], btype='band', output='sos')
        self.y = signal.sosfiltfilt(sos, self.y)
        self.y += baseline
        return self

    # ------------------------------------------------------------------ #
    #  Pipeline execution
    # ------------------------------------------------------------------ #

    def apply(self, history: list) -> "SignalFilter":
        """
        Apply filters in sequence according to the history list.

        Parameters
        ----------
        history : in the form [('DS', (new_fs, is_anti_alias)), ('LP', (cutoff,)), ...]
        """
        for method_key, params in history:
            method_name = self.METHOD_MAP.get(method_key)
            if method_name is None:
                print(tr('pu.unsupported_method', method=method_key))
                continue
            getattr(self, method_name)(*params)
        return self
