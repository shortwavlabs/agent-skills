#!/usr/bin/env python3
"""Estimate causal Conv1D receptive field for an RTNeural-style JSON model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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


def layer_type(layer: dict[str, Any]) -> str:
    value = layer.get("type", layer.get("class_name", ""))
    return str(value).lower()


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


def conv_details(layers: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    details: list[dict[str, int | str]] = []
    for index, layer in enumerate(layers):
        if layer_type(layer) != "conv1d":
            continue

        config = layer.get("config", {})
        source = config if isinstance(config, dict) else layer
        kernel = first_int(source.get("kernel_size", layer.get("kernel_size")), 1)
        dilation = first_int(source.get("dilation_rate", source.get("dilation", layer.get("dilation"))), 1)
        stride = first_int(source.get("strides", source.get("stride", layer.get("stride"))), 1)
        details.append(
            {
                "index": index,
                "name": str(layer.get("name", f"conv1d_{len(details)}")),
                "kernel": max(1, kernel),
                "dilation": max(1, dilation),
                "stride": max(1, stride),
            }
        )
    return details


def calculate_receptive_field(details: list[dict[str, int | str]]) -> tuple[int, list[dict[str, int | str]]]:
    receptive_field = 1
    jump = 1
    rows: list[dict[str, int | str]] = []

    for detail in details:
        kernel = int(detail["kernel"])
        dilation = int(detail["dilation"])
        stride = int(detail["stride"])
        contribution = (kernel - 1) * dilation * jump
        receptive_field += contribution
        rows.append({**detail, "jump": jump, "contribution": contribution, "receptive_field": receptive_field})
        jump *= stride

    return receptive_field, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_json", type=Path, help="Path to an RTNeural/Keras-style JSON model")
    parser.add_argument("--sample-rate", type=float, default=None, help="Optional sample rate for milliseconds")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    with args.model_json.open("r", encoding="utf-8") as handle:
        model = json.load(handle)

    layers = iter_layers(model)
    details = conv_details(layers)
    receptive_field, rows = calculate_receptive_field(details)
    lookback_samples = max(0, receptive_field - 1)
    lookback_ms = None
    if args.sample_rate and args.sample_rate > 0:
        lookback_ms = 1000.0 * lookback_samples / args.sample_rate

    if args.json:
        print(
            json.dumps(
                {
                    "model_json": str(args.model_json),
                    "conv1d_layers": rows,
                    "receptive_field_samples": receptive_field,
                    "lookback_samples": lookback_samples,
                    "lookback_ms": lookback_ms,
                },
                indent=2,
            )
        )
        return 0

    print(f"model: {args.model_json}")
    print(f"conv1d_layers: {len(rows)}")
    print(f"receptive_field_samples: {receptive_field}")
    print(f"lookback_samples: {lookback_samples}")
    if lookback_ms is not None:
        print(f"lookback_ms: {lookback_ms:.3f}")

    if rows:
        print()
        print("idx name kernel dilation stride jump contribution rf")
        for row in rows:
            print(
                f"{row['index']} {row['name']} {row['kernel']} {row['dilation']} "
                f"{row['stride']} {row['jump']} {row['contribution']} {row['receptive_field']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
