"""Read-only Guitar Gear Blender scene audit.

Run inside Blender's Python environment. It prints one JSON object prefixed with
GUITAR_GEAR_AUDIT_JSON=. The script does not modify the scene.

This is a heuristic audit. Warnings must be confirmed visually or against the
product brief before making changes.
"""

from __future__ import annotations

import json
import math

import bpy


SCALE_TOLERANCE = 0.01
LOW_PRODUCT_FOCAL_LENGTH_MM = 45.0


def near_one(value: float) -> bool:
    return abs(abs(value) - 1.0) <= SCALE_TOLERANCE


def object_record(obj: bpy.types.Object) -> dict:
    return {
        "name": obj.name,
        "type": obj.type,
        "dimensions_m": [round(float(v), 6) for v in obj.dimensions],
        "scale": [round(float(v), 6) for v in obj.scale],
        "hide_render": bool(obj.hide_render),
    }


def audit_scene() -> dict:
    scene = bpy.context.scene
    objects = list(scene.objects)
    mesh_objects = [o for o in objects if o.type == "MESH"]
    cameras = [o for o in objects if o.type == "CAMERA"]
    lights = [o for o in objects if o.type == "LIGHT"]

    warnings: list[dict] = []

    for obj in mesh_objects:
        scale = tuple(float(v) for v in obj.scale)
        if any(v < 0 for v in scale):
            warnings.append(
                {
                    "code": "negative-scale",
                    "object": obj.name,
                    "message": "Mesh has negative scale; inspect normals/shading and mirroring intent.",
                }
            )
        elif any(not near_one(v) for v in scale):
            warnings.append(
                {
                    "code": "unapplied-scale",
                    "object": obj.name,
                    "message": "Mesh scale is not approximately 1; bevel/normal behavior may depend on applying scale.",
                }
            )

        if obj.name.startswith(("Cube", "Cylinder", "Sphere", "Plane")) or ".00" in obj.name:
            warnings.append(
                {
                    "code": "default-style-name",
                    "object": obj.name,
                    "message": "Important asset may still have a default/duplicate-style Blender name.",
                }
            )

        visible_material_slots = [slot for slot in obj.material_slots if slot.material]
        if not visible_material_slots and not obj.hide_render:
            warnings.append(
                {
                    "code": "no-material",
                    "object": obj.name,
                    "message": "Render-visible mesh has no assigned material.",
                }
            )

        for mod in obj.modifiers:
            if mod.type == "BOOLEAN" and getattr(mod, "object", None) is None and not getattr(mod, "collection", None):
                warnings.append(
                    {
                        "code": "boolean-missing-operand",
                        "object": obj.name,
                        "modifier": mod.name,
                        "message": "Boolean modifier has no object/collection operand.",
                    }
                )
            if mod.type == "BEVEL" and float(getattr(mod, "width", 0.0)) <= 0.0:
                warnings.append(
                    {
                        "code": "zero-bevel",
                        "object": obj.name,
                        "modifier": mod.name,
                        "message": "Bevel modifier width is zero or negative.",
                    }
                )

    if scene.camera is None:
        warnings.append(
            {
                "code": "no-active-camera",
                "message": "Scene has no active camera.",
            }
        )
    elif scene.camera.type == "CAMERA":
        cam = scene.camera.data
        if cam.type == "PERSP" and float(cam.lens) < LOW_PRODUCT_FOCAL_LENGTH_MM:
            warnings.append(
                {
                    "code": "wide-product-lens",
                    "object": scene.camera.name,
                    "message": f"Active perspective camera is {cam.lens:.1f} mm; inspect for product distortion.",
                }
            )

    area_lights = [o for o in lights if getattr(o.data, "type", None) == "AREA"]
    if len(area_lights) == 0:
        warnings.append(
            {
                "code": "no-area-lights",
                "message": "No area lights found; controlled product reflections may be difficult.",
            }
        )

    if scene.render.engine != "CYCLES":
        warnings.append(
            {
                "code": "non-cycles-engine",
                "message": f"Render engine is {scene.render.engine}; verify this is intentional for final product work.",
            }
        )

    duplicate_material_basenames: dict[str, list[str]] = {}
    for material in bpy.data.materials:
        base = material.name.rsplit(".", 1)[0] if material.name[-4:-3] == "." and material.name[-3:].isdigit() else material.name
        duplicate_material_basenames.setdefault(base, []).append(material.name)
    for base, names in duplicate_material_basenames.items():
        if len(names) > 1:
            warnings.append(
                {
                    "code": "possible-duplicate-materials",
                    "material_base": base,
                    "materials": sorted(names),
                    "message": "Multiple similarly named materials exist; inspect before consolidating.",
                }
            )

    report = {
        "scene": scene.name,
        "units": {
            "system": scene.unit_settings.system,
            "scale_length": scene.unit_settings.scale_length,
            "length_unit": scene.unit_settings.length_unit,
        },
        "render": {
            "engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "resolution_percentage": scene.render.resolution_percentage,
        },
        "counts": {
            "objects": len(objects),
            "meshes": len(mesh_objects),
            "cameras": len(cameras),
            "lights": len(lights),
            "area_lights": len(area_lights),
            "materials": len(bpy.data.materials),
        },
        "active_camera": scene.camera.name if scene.camera else None,
        "objects": [object_record(o) for o in mesh_objects],
        "warnings": warnings,
    }
    return report


if __name__ == "__main__":
    print("GUITAR_GEAR_AUDIT_JSON=" + json.dumps(audit_scene(), sort_keys=True))
