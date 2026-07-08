#!/usr/bin/env python3
"""Estimate harmonic and non-harmonic energy from a coherent sine WAV render."""

from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path


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
            sign = b"\xff" if chunk[2] & 0x80 else b"\x00"
            out.append(int.from_bytes(chunk + sign, "little", signed=True) / 8388608.0)
        return out
    if sample_width == 4:
        count = len(frames) // 4
        return [value / 2147483648.0 for value in struct.unpack("<" + "i" * count, frames)]
    raise ValueError(f"Unsupported sample width: {sample_width}")


def read_wav(path: Path, channel: int, start: int, count: int | None) -> tuple[int, int, list[float]]:
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        total_frames = handle.getnframes()
        if start >= total_frames:
            raise ValueError("settle/start sample is beyond the WAV length")
        handle.setpos(max(0, start))
        frames_to_read = total_frames - start if count is None else min(count, total_frames - start)
        raw = handle.readframes(frames_to_read)

    samples = decode_pcm(raw, sample_width)
    if channel < 0:
        mono: list[float] = []
        for index in range(0, len(samples), channels):
            frame = samples[index : index + channels]
            if len(frame) == channels:
                mono.append(sum(frame) / channels)
        return sample_rate, channels, mono

    if channel >= channels:
        raise ValueError(f"channel {channel} is out of range for {channels} channels")

    selected = [samples[index + channel] for index in range(0, len(samples) - channels + 1, channels)]
    return sample_rate, channels, selected


def coherent_bin_warning(frequency: float, sample_rate: int, length: int) -> tuple[int, float, float]:
    exact = frequency * length / sample_rate
    nearest = int(round(exact))
    error = exact - nearest
    return nearest, exact, error


def dft_bin_energy(samples: list[float], bin_index: int) -> float:
    n = len(samples)
    real = 0.0
    imag = 0.0
    angle_step = -2.0 * math.pi * bin_index / n
    for index, sample in enumerate(samples):
        angle = angle_step * index
        real += sample * math.cos(angle)
        imag += sample * math.sin(angle)
    magnitude_sq = real * real + imag * imag
    if bin_index == 0 or (n % 2 == 0 and bin_index == n // 2):
        return magnitude_sq / n
    return 2.0 * magnitude_sq / n


def safe_db(value: float) -> float:
    return 10.0 * math.log10(max(value, 1.0e-24))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path, help="Rendered WAV from a sine probe")
    parser.add_argument("--fundamental", type=float, required=True, help="Input sine frequency in Hz")
    parser.add_argument("--settle-samples", type=int, default=0, help="Samples to skip before analysis")
    parser.add_argument("--analysis-samples", type=int, default=65536, help="Samples to analyze; 0 means all remaining")
    parser.add_argument("--channel", type=int, default=-1, help="Channel index, or -1 for mono sum")
    parser.add_argument("--max-harmonic", type=int, default=64, help="Maximum harmonic number to count")
    parser.add_argument("--bin-tolerance", type=float, default=0.05, help="Warn when fundamental bin error exceeds this")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    count = None if args.analysis_samples == 0 else max(1, args.analysis_samples)
    sample_rate, channels, samples = read_wav(args.wav, args.channel, max(0, args.settle_samples), count)
    if len(samples) < 16:
        raise SystemExit("Need at least 16 samples for analysis")

    n = len(samples)
    total_energy = sum(sample * sample for sample in samples)
    dc_energy = (sum(samples) * sum(samples)) / n
    fundamental_bin, exact_bin, bin_error = coherent_bin_warning(args.fundamental, sample_rate, n)

    harmonic_rows = []
    harmonic_energy = 0.0
    nyquist = sample_rate * 0.5
    for harmonic in range(1, max(1, args.max_harmonic) + 1):
        frequency = args.fundamental * harmonic
        if frequency >= nyquist:
            break
        bin_index = int(round(frequency * n / sample_rate))
        if bin_index <= 0 or bin_index >= n // 2:
            continue
        energy = dft_bin_energy(samples, bin_index)
        harmonic_energy += energy
        harmonic_rows.append(
            {
                "harmonic": harmonic,
                "frequency_hz": frequency,
                "bin": bin_index,
                "energy": energy,
                "energy_db": safe_db(energy),
            }
        )

    non_harmonic_energy = max(0.0, total_energy - dc_energy - harmonic_energy)
    asr = non_harmonic_energy / max(harmonic_energy, 1.0e-24)
    rms = math.sqrt(total_energy / n)
    peak = max(abs(sample) for sample in samples)

    warnings = []
    if abs(bin_error) > args.bin_tolerance:
        warnings.append(
            f"fundamental is not coherent with analysis window: exact bin {exact_bin:.3f}, nearest {fundamental_bin}"
        )
    if harmonic_energy <= 1.0e-18:
        warnings.append("harmonic energy is near zero; check frequency, silence, or channel selection")
    if peak >= 0.999:
        warnings.append("render is near full-scale clipping; alias report may mix intended clipping with output clipping")

    result = {
        "wav": str(args.wav),
        "sample_rate": sample_rate,
        "channels": channels,
        "analyzed_channel": args.channel,
        "samples": n,
        "fundamental_hz": args.fundamental,
        "fundamental_bin": fundamental_bin,
        "fundamental_exact_bin": exact_bin,
        "fundamental_bin_error": bin_error,
        "rms_dbfs": 20.0 * math.log10(max(rms, 1.0e-12)),
        "peak": peak,
        "total_energy": total_energy,
        "dc_energy": dc_energy,
        "harmonic_energy": harmonic_energy,
        "non_harmonic_energy": non_harmonic_energy,
        "alias_to_signal_ratio": asr,
        "alias_to_signal_db": safe_db(asr),
        "harmonics": harmonic_rows,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    for key in (
        "wav",
        "sample_rate",
        "channels",
        "analyzed_channel",
        "samples",
        "fundamental_hz",
        "fundamental_exact_bin",
        "fundamental_bin_error",
        "rms_dbfs",
        "peak",
        "harmonic_energy",
        "non_harmonic_energy",
        "alias_to_signal_ratio",
        "alias_to_signal_db",
    ):
        value = result[key]
        if isinstance(value, float):
            print(f"{key}: {value:.9g}")
        else:
            print(f"{key}: {value}")

    if warnings:
        print()
        print("warnings:")
        for warning in warnings:
            print(f"- {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
