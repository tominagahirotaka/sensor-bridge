"""Tests for plot.py's module-level pure-logic helpers: merging the default
filter with the interactive SignalSmoothingWindow's history, and resolving
which graph types a given board supports."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import plot as plotmod  # noqa: E402


class TestMergeFilterAndHistory:
    def test_filter_comes_before_history_for_the_same_channel(self):
        filter_dict = {0: [["LP", [10]]]}
        history_dict = {0: [["MA", [5]]]}
        merged = plotmod.merge_filter_and_history(filter_dict, history_dict)
        assert merged[0] == [["LP", [10]], ["MA", [5]]]

    def test_channel_only_in_filter_is_preserved(self):
        merged = plotmod.merge_filter_and_history({0: [["LP", [10]]]}, {})
        assert merged[0] == [["LP", [10]]]

    def test_channel_only_in_history_is_preserved(self):
        merged = plotmod.merge_filter_and_history({}, {0: [["MA", [5]]]})
        assert merged[0] == [["MA", [5]]]

    def test_both_empty_gives_empty_dict(self):
        assert plotmod.merge_filter_and_history({}, {}) == {}

    def test_multiple_channels_merged_independently(self):
        merged = plotmod.merge_filter_and_history(
            {0: [["LP", [10]]], 1: [["LP", [20]]]},
            {0: [["MA", [5]]]},
        )
        assert merged[0] == [["LP", [10]], ["MA", [5]]]
        assert merged[1] == [["LP", [20]]]


class TestResolveGraphVisibility:
    def test_matching_board_restricts_to_its_allowed_graphs(self):
        graph_lst = {"LIS3DH": ["Timeseries", "PowerSpectra"]}
        graph_name = ["0:Timeseries", "1:PowerSpectra", "2:Scalogram"]
        result = plotmod.resolve_graph_visibility("Accelerometer(LIS3DH)", graph_lst, graph_name)
        assert result == [True, True, False]

    def test_unmatched_board_shows_every_graph(self):
        graph_lst = {"LIS3DH": ["Timeseries"]}
        graph_name = ["0:Timeseries", "1:PowerSpectra"]
        result = plotmod.resolve_graph_visibility("SomeUnknownBoard", graph_lst, graph_name)
        assert result == [True, True]

    def test_match_is_substring_based(self):
        # board_prog is the full title string; the graph_lst key just needs
        # to appear somewhere in it (e.g. "DPG(X95840W)+LIS3DHx2").
        graph_lst = {"LIS3DH": ["Timeseries"]}
        graph_name = ["0:Timeseries", "1:PowerSpectra"]
        result = plotmod.resolve_graph_visibility(
            "DPG(X95840W)+LIS3DHx2", graph_lst, graph_name)
        assert result == [True, False]
