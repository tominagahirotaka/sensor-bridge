#!/usr/bin/env python3
"""Helpers for sensor-bridge processed binary files."""

from __future__ import annotations

import copy
import io
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


RAW_MAGIC = b"HS"
PROCESSED_MAGIC = b"HP"
HEADER_SIZE_BYTES = 2
PROCESSED_FORMAT_VERSION = 1


class ProcessedBinaryError(RuntimeError):
    """Raised when processed binary files cannot be encoded or decoded safely."""


def _write_container(destination: Path, magic: bytes, header: Any, payload: bytes) -> None:
    if len(magic) != 2:
        raise ProcessedBinaryError("container magic must be 2 bytes")
    header_bytes = pickle.dumps(header, protocol=pickle.HIGHEST_PROTOCOL)
    if len(header_bytes) > 0xFFFF:
        raise ProcessedBinaryError("pickled header exceeds 65535 bytes")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(magic)
            stream.write(len(header_bytes).to_bytes(HEADER_SIZE_BYTES, "big"))
            stream.write(header_bytes)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _normalize_label(label: Any, index: int) -> dict[str, str]:
    if isinstance(label, dict) and "left" in label:
        name, unit = label["left"]
        return {"name": str(name), "unit": str(unit)}
    return {"name": f"series_{index}", "unit": ""}


def build_processed_header(source_header: Any, plot_data: Any,
                           filter_history: dict[int, list[Any]], source_file: Path) -> Any:
    header = copy.deepcopy(source_header)
    series_meta = [_normalize_label(label, index) for index, label in enumerate(plot_data.labels)]
    x_name, x_unit = plot_data.xlabel["bottom"] if plot_data.xlabel else ("time", "")

    header.processed_data = {
        "format_name": "sensor-bridge-processed-timeseries",
        "format_version": PROCESSED_FORMAT_VERSION,
        "payload_format": "npz",
        "time_axis": {"name": str(x_name), "unit": str(x_unit)},
        "series": series_meta,
        "filter_history": filter_history,
        "source_file": source_file.name,
        "series_count": len(series_meta),
    }
    if isinstance(getattr(header, "env_set", None), dict):
        env_set = dict(header.env_set)
        title = str(env_set.get("title", "sensor-bridge"))
        if "Processed" not in title:
            env_set["title"] = f"{title} Processed"
        header.env_set = env_set
    return header


def encode_processed_payload(plot_data: Any) -> bytes:
    buffer = io.BytesIO()
    arrays: dict[str, np.ndarray] = {}
    for index, (series, label) in enumerate(zip(plot_data.data, plot_data.labels)):
        x, y = series
        arrays[f"x_{index}"] = np.asarray(x, dtype=np.float64)
        arrays[f"y_{index}"] = np.asarray(y, dtype=np.float64)
    np.savez(buffer, **arrays)
    return buffer.getvalue()


def write_processed_record(
        dat_destination: Path,
        cpt_destination: Path,
        header: Any,
        plot_data: Any) -> None:
    payload = encode_processed_payload(plot_data)
    _write_container(dat_destination, PROCESSED_MAGIC, header, payload)
    _write_container(cpt_destination, PROCESSED_MAGIC, header, b"")


def decode_processed_payload(
        payload: bytes, metadata: dict[str, Any]) -> list[tuple[np.ndarray, np.ndarray]]:
    payload_format = metadata.get("payload_format")
    if payload_format != "npz":
        raise ProcessedBinaryError(f"unsupported processed payload format: {payload_format}")
    expected = int(metadata.get("series_count", 0))
    if expected <= 0:
        raise ProcessedBinaryError("processed header has no series_count")

    with np.load(io.BytesIO(payload), allow_pickle=False) as arrays:
        series: list[tuple[np.ndarray, np.ndarray]] = []
        for index in range(expected):
            x_name = f"x_{index}"
            y_name = f"y_{index}"
            if x_name not in arrays or y_name not in arrays:
                raise ProcessedBinaryError(f"processed payload is missing series {index}")
            series.append((np.array(arrays[x_name]), np.array(arrays[y_name])))
    return series
