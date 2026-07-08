#!/usr/bin/env python3
"""Compare two WAV files with alignment, residual, and correlation metrics."""

from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path
from typing import Iterable


def decode_pcm(frames: bytes, sample_width: int) -> list[float]:
    if sample_width == 1:
        return [(byte - 128) / 128.0 for byte in frames]
    if sample_width == 2:
        count = len(frames) // 2
        return [value / 32768.0 for value in struct.unpack("<" + "h" * count, frames)]
    if sample_width == 3:
        out: list[float] = []
        for index in range(0, len(frames), 3):
            chunk = frames[index : index + 3]
            if len(chunk) < 3:
                break
            value = int.from_bytes(chunk + (b"\xff" if chunk[2] & 0x80 else b"\x00"), "little", signed=True)
            out.append(value / 8388608.0)
        return out
    if sample_width == 4:
        count = len(frames) // 4
        return [value / 2147483648.0 for value in struct.unpack("<" + "i" * count, frames)]
    raise ValueError(f"Unsupported sample width: {sample_width}")


def read_wav_mono(path: Path, limit_samples: int | None) -> tuple[int, int, list[float]]:
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        total_frames = handle.getnframes()
        frames_to_read = total_frames if limit_samples is None else min(total_frames, limit_samples)
        raw = handle.readframes(frames_to_read)

    samples = decode_pcm(raw, sample_width)
    mono: list[float] = []
    for index in range(0, len(samples), channels):
        frame = samples[index : index + channels]
        if len(frame) == channels:
            mono.append(sum(frame) / channels)

    return sample_rate, channels, mono


def aligned_pairs(reference: list[float], candidate: list[float], lag: int) -> Iterable[tuple[float, float]]:
    if lag >= 0:
        count = min(len(reference), len(candidate) - lag)
        for index in range(max(0, count)):
            yield reference[index], candidate[index + lag]
    else:
        shift = -lag
        count = min(len(reference) - shift, len(candidate))
        for index in range(max(0, count)):
            yield reference[index + shift], candidate[index]


def dot_for_lag(reference: list[float], candidate: list[float], lag: int, window: int) -> float:
    total = 0.0
    count = 0
    for a, b in aligned_pairs(reference, candidate, lag):
        total += a * b
        count += 1
        if count >= window:
            break
    return total


def best_lag(reference: list[float], candidate: list[float], max_shift: int, alignment_samples: int) -> int:
    best = 0
    best_abs_dot = -1.0
    window = max(1, alignment_samples)
    for lag in range(-max_shift, max_shift + 1):
        value = abs(dot_for_lag(reference, candidate, lag, window))
        if value > best_abs_dot:
            best = lag
            best_abs_dot = value
    return best


def safe_db(value: float) -> float:
    return 20.0 * math.log10(max(value, 1.0e-12))


def metrics(reference: list[float], candidate: list[float], lag: int) -> dict[str, float | int | str]:
    pairs = list(aligned_pairs(reference, candidate, lag))
    if not pairs:
        raise ValueError("No overlapping samples after alignment")

    n = len(pairs)
    ref_energy = sum(a * a for a, _ in pairs)
    cand_energy = sum(b * b for _, b in pairs)
    dot = sum(a * b for a, b in pairs)
    residual_energy = sum((b - a) * (b - a) for a, b in pairs)
    inverted_residual_energy = sum((-b - a) * (-b - a) for a, b in pairs)
    peak_error = max(abs(b - a) for a, b in pairs)
    ref_rms = math.sqrt(ref_energy / n)
    cand_rms = math.sqrt(cand_energy / n)
    rmse = math.sqrt(residual_energy / n)
    esr = residual_energy / max(ref_energy, 1.0e-24)
    correlation = dot / math.sqrt(max(ref_energy * cand_energy, 1.0e-24))
    polarity = "normal" if residual_energy <= inverted_residual_energy else "inverted"
    mean_ref = sum(a for a, _ in pairs) / n
    mean_cand = sum(b for _, b in pairs) / n

    return {
        "samples_compared": n,
        "lag_samples": lag,
        "polarity": polarity,
        "reference_rms_dbfs": safe_db(ref_rms),
        "candidate_rms_dbfs": safe_db(cand_rms),
        "rmse": rmse,
        "rmse_dbfs": safe_db(rmse),
        "normalized_rmse": rmse / max(ref_rms, 1.0e-12),
        "esr": esr,
        "correlation": correlation,
        "peak_error": peak_error,
        "reference_dc": mean_ref,
        "candidate_dc": mean_cand,
        "dc_error": mean_cand - mean_ref,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="Reference WAV")
    parser.add_argument("candidate", type=Path, help="Candidate WAV")
    parser.add_argument("--max-shift", type=int, default=0, help="Search +/- samples for best alignment")
    parser.add_argument("--alignment-samples", type=int, default=24000, help="Samples used for lag search")
    parser.add_argument("--limit-samples", type=int, default=960000, help="Limit decoded frames; use 0 for all")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    limit = None if args.limit_samples == 0 else max(1, args.limit_samples)
    ref_rate, ref_channels, reference = read_wav_mono(args.reference, limit)
    cand_rate, cand_channels, candidate = read_wav_mono(args.candidate, limit)

    if ref_rate != cand_rate:
        raise SystemExit(f"Sample-rate mismatch: {ref_rate} vs {cand_rate}")

    lag = best_lag(reference, candidate, max(0, args.max_shift), max(1, args.alignment_samples))
    result = metrics(reference, candidate, lag)
    result.update(
        {
            "reference": str(args.reference),
            "candidate": str(args.candidate),
            "sample_rate": ref_rate,
            "reference_channels": ref_channels,
            "candidate_channels": cand_channels,
        }
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    for key in (
        "reference",
        "candidate",
        "sample_rate",
        "reference_channels",
        "candidate_channels",
        "samples_compared",
        "lag_samples",
        "polarity",
        "reference_rms_dbfs",
        "candidate_rms_dbfs",
        "rmse",
        "rmse_dbfs",
        "normalized_rmse",
        "esr",
        "correlation",
        "peak_error",
        "reference_dc",
        "candidate_dc",
        "dc_error",
    ):
        value = result[key]
        if isinstance(value, float):
            print(f"{key}: {value:.9g}")
        else:
            print(f"{key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
