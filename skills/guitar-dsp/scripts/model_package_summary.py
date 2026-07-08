#!/usr/bin/env python3
"""Summarize an RTNeural model JSON or package folder and surface warnings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SKIP_RECURSE_KEYS = {"weights", "bias", "biases", "kernel", "kernels"}


def load_json(path: Path) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def find_model_json(path: Path) -> Path | None:
    if path.is_file():
        return path

    preferred = sorted(path.glob("*.rtneural.json"))
    if preferred:
        return preferred[0]

    candidates = [p for p in sorted(path.glob("*.json")) if p.name not in {"metadata.json", "manifest.json"}]
    return candidates[0] if candidates else None


def first_int(value: Any, default: int = 1) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, list) and value:
        return first_int(value[0], default)
    if isinstance(value, dict):
        for key in ("0", "value", "size", "kernel_size", "dilation", "stride"):
            if key in value:
                return first_int(value[key], default)
    return default


def iter_layers(obj: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "type" in node or "class_name" in node:
                found.append(node)
            for key in ("layers", "model", "config", "children"):
                child = node.get(key)
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    walk(item)

    walk(obj)
    return found


def layer_type(layer: dict[str, Any]) -> str:
    return str(layer.get("type", layer.get("class_name", ""))).lower()


def receptive_field(layers: list[dict[str, Any]]) -> tuple[int, int]:
    rf = 1
    jump = 1
    conv_count = 0
    for layer in layers:
        if layer_type(layer) != "conv1d":
            continue
        config = layer.get("config", {})
        source = config if isinstance(config, dict) else layer
        kernel = max(1, first_int(source.get("kernel_size", layer.get("kernel_size")), 1))
        dilation = max(1, first_int(source.get("dilation_rate", source.get("dilation", layer.get("dilation"))), 1))
        stride = max(1, first_int(source.get("strides", source.get("stride", layer.get("stride"))), 1))
        rf += (kernel - 1) * dilation * jump
        jump *= stride
        conv_count += 1
    return rf, conv_count


def find_values(obj: Any, keys: set[str], limit: int = 8) -> list[Any]:
    matches: list[Any] = []

    def walk(node: Any) -> None:
        if len(matches) >= limit:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                key_lower = str(key).lower()
                if key_lower in keys:
                    matches.append(value)
                    if len(matches) >= limit:
                        return
                if key_lower not in SKIP_RECURSE_KEYS and isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    walk(item)

    walk(obj)
    return matches


def first_value(obj: Any, names: list[str]) -> Any | None:
    values = find_values(obj, {name.lower() for name in names}, limit=1)
    return values[0] if values else None


def collect_sidecars(path: Path, model_path: Path) -> dict[str, Any]:
    root = path if path.is_dir() else model_path.parent
    sidecars: dict[str, Any] = {}
    for candidate in sorted(root.glob("*.json")):
        if candidate == model_path:
            continue
        lower = candidate.name.lower()
        if any(token in lower for token in ("metadata", "manifest", "validation", "benchmark", "alias", "report", "metrics")):
            data = load_json(candidate)
            if data is not None:
                sidecars[candidate.name] = data
    return sidecars


def flattened_payload(model: Any, sidecars: dict[str, Any]) -> dict[str, Any]:
    return {"model": model, "sidecars": sidecars}


def format_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def warning_list(summary: dict[str, Any], host_sample_rate: float | None) -> list[str]:
    warnings: list[str] = []
    if summary.get("sample_rate") in (None, "unknown"):
        warnings.append("sample rate metadata is missing")
    elif host_sample_rate and abs(float(summary["sample_rate"]) - host_sample_rate) > 1.0:
        warnings.append(f"model sample rate {summary['sample_rate']} differs from host {host_sample_rate:g}")

    if summary.get("validation_status") in (None, "unknown"):
        warnings.append("validation status is missing")
    elif str(summary["validation_status"]).lower() not in {"pass", "passed", "ok", "true"}:
        warnings.append(f"validation status is {summary['validation_status']}")

    if summary.get("aliasing_status") not in (None, "unknown") and str(summary["aliasing_status"]).lower() not in {"pass", "passed", "ok", "true"}:
        warnings.append(f"aliasing status is {summary['aliasing_status']}")

    rtf = summary.get("real_time_factor")
    if isinstance(rtf, (int, float)) and rtf > 0.75:
        warnings.append(f"native real-time factor is high ({rtf:.3g})")

    if summary.get("conv1d_layers", 0) == 0:
        warnings.append("no Conv1D layers found; receptive field may not be meaningful")

    if not summary.get("sidecar_files"):
        warnings.append("no metadata/validation/benchmark sidecars found")

    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="RTNeural JSON file or package folder")
    parser.add_argument("--host-sample-rate", type=float, default=None, help="Warn when metadata differs")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    model_path = find_model_json(args.path)
    if model_path is None:
        raise SystemExit(f"No model JSON found at {args.path}")

    model = load_json(model_path)
    if model is None:
        raise SystemExit(f"Could not parse JSON: {model_path}")

    sidecars = collect_sidecars(args.path, model_path)
    payload = flattened_payload(model, sidecars)
    layers = iter_layers(model)
    rf, conv_count = receptive_field(layers)

    sample_rate = first_value(payload, ["sample_rate", "sampleRate", "sr", "training_sample_rate"])
    validation_status = first_value(payload, ["validation_status", "validationStatus", "status"])
    aliasing_status = first_value(payload, ["aliasing_status", "aliasingStatus"])
    real_time_factor = first_value(payload, ["real_time_factor", "realTimeFactor", "rtf"])
    latency = first_value(payload, ["latency_samples", "latencySamples", "alignment_latency_samples"])
    esr = first_value(payload, ["esr", "error_to_signal_ratio"])
    rmse = first_value(payload, ["rmse"])
    correlation = first_value(payload, ["correlation", "corr"])
    asr = first_value(payload, ["asr", "aliasing_to_signal_ratio"])
    input_size = first_value(model, ["input_size", "in_size"])
    output_size = first_value(model, ["output_size", "out_size"])

    summary: dict[str, Any] = {
        "path": str(args.path),
        "model_json": str(model_path),
        "sidecar_files": sorted(sidecars.keys()),
        "layers": len(layers),
        "conv1d_layers": conv_count,
        "receptive_field_samples": rf,
        "lookback_samples": max(0, rf - 1),
        "sample_rate": sample_rate,
        "input_size": input_size,
        "output_size": output_size,
        "latency_samples": latency,
        "validation_status": validation_status,
        "esr": esr,
        "rmse": rmse,
        "correlation": correlation,
        "aliasing_status": aliasing_status,
        "asr": asr,
        "real_time_factor": real_time_factor,
    }
    summary["warnings"] = warning_list(summary, args.host_sample_rate)

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    for key in (
        "model_json",
        "sidecar_files",
        "layers",
        "conv1d_layers",
        "receptive_field_samples",
        "lookback_samples",
        "sample_rate",
        "input_size",
        "output_size",
        "latency_samples",
        "validation_status",
        "esr",
        "rmse",
        "correlation",
        "aliasing_status",
        "asr",
        "real_time_factor",
    ):
        print(f"{key}: {format_value(summary.get(key))}")

    if summary["warnings"]:
        print()
        print("warnings:")
        for warning in summary["warnings"]:
            print(f"- {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
