#!/usr/bin/env python3
"""General-purpose helpers shared across get.py/plot.py: .ini loading, the
board 'struct' protocol mini-language, age/heart-rate calculations used by
the subject dialog, and peak detection."""

import configparser
import datetime
import math
import re

import numpy as np


def read_setting_ini(fname):
    """Load a board .ini file, returning (env_set, code) dicts.

    `env_set` merges every section except [code]; `code` holds the
    exec()'d/eval()'d GUI snippets from the [code] section, keyed by name
    (e.g. 'figs', 'panel1', 'menubar').
    """
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str    # preserve case (don't lowercase keys)
    ini.read(fname, 'UTF-8')
    env_set, code = {}, {}
    for sec in ini.sections():
        if sec == 'code':
            code = dict(ini.items(sec))
        else:
            env_set.update(dict(ini.items(sec)))
    return env_set, code


def join_dict(dic, sep1, sep2):
    """Join a dict into 'k1=v1<sep1>k2=v2<sep1>...' (the wire format the boards use)."""
    return sep1.join([key + sep2 + str(val) for key, val in dic.items()])


def repeat_interpret(s, sep=',', paren_count='[]', paren_content='{}'):
    """Expand the board 'struct' mini-language's repeat groups.

    "time(u4:func0), [(line0,line1)]{temp(u2:func1),humid(u2:func2)}"
    -> ['time(u4:func0)', 'temp(u2:func1)line0', 'humid(u2:func2)line0',
        'temp(u2:func1)line1', 'humid(u2:func2)line1']
    """
    tmp_str = s.replace(' ', '')
    start = tmp_str.find(paren_count[0])
    end = tmp_str.find(paren_count[1])
    tmp_lst = tmp_str.split(sep) if start == -1 else []
    end2 = -1
    while start >= 0:
        if tmp_str[start + 1] == '(':
            sub_lst = tmp_str[start + 2:end - 1].rstrip(',').split(',')
        else:
            sub_lst = [str(i) for i in range(int(tmp_str[start + 1:end]))]

        tmp_lst += tmp_str[end2 + 1:start - 1].split(sep) if start != 0 else []
        if tmp_str[end + 1] == paren_content[0]:
            end2 = tmp_str.find(paren_content[1], start)
            tmp2 = tmp_str[end + 2:end2].split(sep)
        else:
            end2 = tmp_str.find(sep, end + 1)
            tmp2 = [tmp_str[end + 1:end2]] if end2 > 0 else [tmp_str[end + 1:]]
        for sub in sub_lst:
            tmp_lst += list(map(lambda x: x + sub, tmp2))
        start = tmp_str.find(paren_count[0], start + 1)
        end = tmp_str.find(paren_count[1], end + 1)

    if end2 > 0:
        tmp_lst += tmp_str[end2 + 1:].split(sep)
    return [a for a in tmp_lst if a != '']


def content_process(s, kind=''):
    """Parse one 'name(u2:func1)suffix' struct token.

    kind='label' : 'temp(u2:func1)0'  -> ('temp', '0')
    kind='byte'  : 'temp(u2:func1)0'  -> 2
    kind='func'  : 'temp(u2:func1)0'  -> 1
    """
    tmp = re.findall(r'(\w*)\((\w*):(\w*)\)(\w*)$', s)
    if 'lab' in kind:  # label
        return (tmp[0][0], tmp[0][3])
    elif 'byte' in kind:
        return int(tmp[0][1][1:])
    elif 'fun' in kind:
        name, number = re.findall(r'^([A-z]*)(\d*)$', tmp[0][2])[0]
        return int(number)
    return tmp[0]


def make_struct_list(struct):
    """Turn the expanded struct token list into [label, (start, end), func_index] rows.

    From  ['time(u4:func0)',    'port(u2:func1)0',    'port(u2:func1)1',    'port(u2:func1)2']
    To    [['time', (0, 4), 0], ['port0', (4, 6), 1], ['port1', (6, 8), 1], ['port2', (8, 10), 1]]
    """
    def byte_separation(lst):     # [4,2,2,2] -> [(0,4), (4,6), (6,8), (8,10)]
        tmp = [(0, lst[0])]
        cnt = lst[0]
        for i in range(1, len(lst)):
            tmp.append((cnt, cnt + lst[i]))
            cnt += lst[i]
        return tmp

    lab = [content_process(s, kind='label') for s in struct]
    loc = byte_separation([content_process(s, kind='byte') for s in struct])
    fun = [content_process(s, kind='func') for s in struct]
    combined = [[x, y, z] for (x, y, z) in zip(lab, loc, fun)]
    return combined


def calc_age_now(birthday: str) -> int:
    """Age in whole years as of right now, from a 'YYYY/MM/DD'-style birthday string."""
    now = datetime.datetime.now()
    return calc_age(birthday, now)


def calc_age(birthday: str, day: datetime.datetime) -> int:
    """Age in whole years on `day`, from a 'YYYY/MM/DD'-style birthday string."""
    day_int = int(day.strftime("%Y%m%d"))
    birth_digit = birthday.replace('/', '')
    if not (birth_digit.isdigit() and len(birth_digit) == 8):
        return 0
    birth_int = int(birth_digit)
    return math.floor((day_int - birth_int) / 10000)


def calc_target_Calbonen_age(age, resting_heart_rate, strength):
    """Target heart rate via the Karvonen formula, given age directly."""
    try:
        HR = int(resting_heart_rate)
    except (ValueError, TypeError):
        HR = 0
    return (220 - age - HR) * strength / 100 + HR


def find_peaks(a, amp_thre, local_width=1, min_peak_distance=1):
    """
    Detect peaks in an array, given an amplitude threshold, the local window
    width used to judge local maxima/minima, and the minimum peak distance.
    Peak distance is tracked separately for positive and negative peaks
    internally, so nearby positive and negative peaks are both detected.
    :rtype (int, float)
    :return ndarray of peak indices
    """
    # generate candidate indices to limit by threthold
    idxs = np.where(np.abs(a) > amp_thre)[0]

    # extend array to decide local maxima/minimum
    idxs_with_offset = idxs + local_width
    a_extend = np.r_[[a[0]] * local_width, a, [a[-1]] * local_width]

    last_pos_peak_idx = last_neg_peak_idx = 0
    result_idxs = []

    for i in idxs_with_offset:
        is_local_maximum = (a_extend[i] >= 0 and
                            a_extend[i] >= np.max(a_extend[i - local_width: i + local_width + 1]))
        is_local_minimum = (a_extend[i] < 0 and
                            a_extend[i] <= np.min(a_extend[i - local_width: i + local_width + 1]))
        if (is_local_maximum or is_local_minimum):
            if is_local_minimum:
                if i - last_pos_peak_idx > min_peak_distance:
                    result_idxs.append(i)
                    last_pos_peak_idx = i
            else:
                if i - last_neg_peak_idx > min_peak_distance:
                    result_idxs.append(i)
                    last_neg_peak_idx = i
    result_idxs = np.array(result_idxs) - local_width
    return result_idxs


def average_heart_rate(bloodP):
    """Average of the numeric heart-rate readings in the subject dialog's blood-pressure rows.
    Returns 0 when no row has a numeric reading (e.g. the field was left blank), matching
    calc_target_Calbonen_age()'s own no-data-> 0 fallback (the two are used together)."""
    vals = [int(val[3]) for val in bloodP if val[3].isdigit()]
    return np.average(vals) if vals else 0
