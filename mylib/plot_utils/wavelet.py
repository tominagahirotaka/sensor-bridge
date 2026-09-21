"""Wavelet/frequency-domain analysis: WaveletParams + do_wavelet_transform
(continuous wavelet transform -> scalogram), power spectrum, and the
peak/valley-based time-varying frequency & amplitude estimation."""

import json
from dataclasses import asdict, dataclass, field

import numpy as np
import scipy.signal as signal

from mylib.i18n import t as tr
from mylib.plot_utils.reading import PlotData, PlotImageData


def do_compute_time_varying_freq_amp(xy):
    pv_freq = PlotData()
    pv_freq.xlabel = xy.xlabel
    pv_freq.title = 'Freq. from peaks & valleys'
    pv_freq.subtitle = tr('pu.prominence_10pct')
    pv_amp = PlotData()
    pv_amp.xlabel = pv_freq.xlabel
    pv_amp.title = 'Amp. from peaks & valleys'
    pv_amp.subtitle = pv_freq.subtitle
    energy = PlotData()
    energy.title = 'Energy from peaks & valleys'
    energy.subtitle = pv_freq.subtitle
    energy.xlabel = pv_freq.xlabel
    power = PlotData()
    power.title = 'Power from peaks & valleys'
    power.subtitle = pv_freq.subtitle
    power.xlabel = pv_freq.xlabel
    for (x, y), l in zip(xy.data, xy.labels):
        prominence_value = 0.1 * (np.max(y) - np.min(y))
        peaks, _ = signal.find_peaks(y, height=None, distance=None, prominence=prominence_value)
        valleys, _ = signal.find_peaks(-y, height=None, distance=None, prominence=prominence_value)
        time, freq, amp = compute_time_varying_freq_amp(x, y, peaks, valleys)
        lab = {k: (v[0], '') for k, v in l.items()}
        pv_freq.add_series(time, freq, label=lab)
        pv_amp.add_series(time, amp, label=lab)
        # compute energy & power
        energy.add_series(time, (amp * freq)**2, label=lab)
        power.add_series(time, amp**2, label=lab)
    return pv_freq, pv_amp, energy, power

# Class for the wavelet transform


@dataclass
class WaveletParams:
    # rangeOfFreq = [1.2, 2.2, 0.001] # frequency [min, max, step]
    range: list = field(default_factory=lambda: [1.2, 3.0, 0.01])
    omega0: float = 6

    def __post_init__(self):
        if not (isinstance(self.range, (list, tuple)) and len(self.range) == 3):
            raise ValueError("range must be a list of 3 numbers [start, stop, step]")
        if self.range[2] <= 0 or self.omega0 <= 0:
            raise ValueError("range step and omega0 must be > 0")
        if self.range[0] >= self.range[1]:
            raise ValueError("range[0] must be less than range[1]")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    @classmethod
    def from_json(cls, filepath):
        with open(filepath, "r") as f:
            return cls.from_dict(json.load(f))

    def to_json(self, filepath):
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f)

    def __repr__(self):
        return f"[INFO] WaveletParams(range={self.range}, omega0={self.omega0})"

    def __str__(self):
        return self.__repr__()

# wavelet transform


def do_wavelet_transform(xy, params: WaveletParams = WaveletParams()):
    data_skip = 2
    wv_data = PlotImageData()
    wv_data.xlabel = xy.xlabel
    wv_data.title = 'Scalogram'
    print(params)
    wv_data.subtitle = params  # f'{params.range=},{params.omega0=}'
    energy = PlotData()
    energy.title = 'Energy'
    energy.xlabel = wv_data.xlabel
    power = PlotData()
    power.title = 'Power'
    power.subtitle = wv_data.subtitle
    power.xlabel = wv_data.xlabel
    max_power_freq = PlotData()
    max_power_freq.title = 'Max power freq.'
    max_power_freq.subtitle = wv_data.subtitle
    max_power_freq.xlabel = wv_data.xlabel
    max_power_bpm = PlotData()
    max_power_bpm.title = 'Max power BPM'
    max_power_bpm.subtitle = wv_data.subtitle
    max_power_bpm.xlabel = wv_data.xlabel

    for (x, y), l in zip(xy.data, xy.labels):
        # wavelet transform (data is decimated by half since swan can't handle the full rate)
        x_sub = x[data_skip:-data_skip - 1:data_skip]
        y_sub = y[data_skip:-data_skip - 1:data_skip]
        # run the continuous wavelet transform
        freq, result = calc_wavelet(x_sub, y_sub, params)
        lab = {k: (v[0], 'Hz') for k, v in l.items()}
        wv_data.add_series(x_sub, freq, result, label=lab)
        # compute energy & power & max power freq
        lab = {k: (v[0], '') for k, v in l.items()}
        energy.add_series(x_sub, ene := np.sum((result.T * freq)**2, axis=1), label=lab)
        lab = {k: (v[0], '') for k, v in l.items()}
        power.add_series(x_sub, np.sum(result.T**2, axis=1), label=lab)
        lab = {k: (v[0], 'Hz') for k, v in l.items()}
        # get the index of the max power at each time step
        max_power_indices = np.argmax(result, axis=0)  # shape: (n_times,)
        # get the frequency corresponding to that index
        dominant_freqs = freq[max_power_indices]     # shape: (n_times,)
        threshold = 0.1 * np.max(result)  # 10% of the max value
        # dominant_freqs_filtered = np.where(
        #     power[max_power_indices, np.arange(result.shape[1])] > threshold,
        #     freqs[max_power_indices],
        #     np.nan  # NaN below the threshold
        # )
#        max_power_freq.add_series(x_sub, dominant_freqs_filtered, label=lab)
        max_power_freq.add_series(x_sub, dominant_freqs, label=lab)
        lab = {k: (v[0], 'bpm') for k, v in l.items()}
        max_power_bpm.add_series(x_sub, dominant_freqs * 60, label=lab)

    return wv_data, energy, power, max_power_freq, max_power_bpm


def do_power_spectrum(xy):
    ps = PlotData()
    ps.xlabel = {'bottom': ('Freq', 'Hz')}
    ps.title = 'Power Spectra'
    ps.subtitle = ''
    for (x, y), l in zip(xy.data, xy.labels):
        freq, power = compute_power_spectrum(x, y)
        lab = {k: (v[0], '') for k, v in l.items()}
        ps.add_series(freq, power, label=lab)

    return ps


def compute_power_spectrum(x, y):
    """
    Function to compute the power spectrum.
    Parameters:
        x (array-like): the time axis or x axis (ideally evenly spaced)
        y (array-like): the signal data (y axis)

    Returns:
        freqs (ndarray): frequency components
        power (ndarray): power spectrum (amplitude squared)
    """
    x = np.asarray(x)
    y = np.asarray(y)

    # sampling interval (estimated from the mean)
    dt = np.mean(np.diff(x))
    fs = 1.0 / dt  # sampling frequency
    # FFT
    fft_vals = np.fft.fft(y)
    fft_freqs = np.fft.fftfreq(len(y), d=dt)
    # power spectrum (positive frequencies only)
    positive_freqs = fft_freqs > 0
    freqs = fft_freqs[positive_freqs]
    power = np.abs(fft_vals[positive_freqs])**2 / len(y)
    return freqs, power


def pair_peaks_valleys(peaks, valleys):
    """Pair each peak with its nearest valley"""
    pairs = []
    for p in peaks:
        # find the valley with the smallest distance
        if len(valleys) == 0:
            continue
        idx = np.argmin(np.abs(valleys - p))
        v = valleys[idx]
        # register regardless of left/right order
        pairs.append((min(p, v), max(p, v)))
    return pairs


def compute_time_varying_freq_amp(t, y, peaks, valleys):
    pairs = pair_peaks_valleys(peaks, valleys)

    freqs = []
    amps = []
    times = []

    for i, (i1, i2) in enumerate(pairs):
        try:
            if np.isnan(y[i1]) or np.isnan(y[i2]):
                continue
            dt = np.abs(t[i2] - t[i1])
            dy = np.abs(y[i2] - y[i1])
            if dt == 0:
                continue
            freqs.append(1.0 / dt)
            amps.append(dy / 2)
            times.append((t[i1] + t[i2]) / 2)
        except Exception as e:
            print(tr('pu.error_at_pair', i=i, err=e))
            continue

    return np.array(times), np.array(freqs), np.array(amps)

####
# Return the index of the value in array closest to value


def calc_wavelet(x, y, params):
    from swan import pycwt   # must be installed via pip install swan
    dt = (x[-1] - x[0]) / (len(x) - 1)
    Fs = 1 / dt
    freqs = np.arange(*params.range)
    wavelet = pycwt.Morlet(params.omega0)    # create the Morlet wavelet
    r = pycwt.cwt_f(y, freqs, Fs, wavelet)
    return freqs, np.abs(r)
