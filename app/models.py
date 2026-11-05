"""Definisi key setting, metadata, dan helper format."""

from __future__ import annotations

import re

# Key yang dikelola aplikasi ini.
MANAGED_KEYS: tuple[str, ...] = (
    "resolution_mode",
    "resolution_width.custom",
    "resolution_height.custom",
    "resolution_dpi.custom",
    "max_frame_rate",
    "dynamic_adjust_frame_rate",
    "dynamic_low_frame_rate_limit",
    "vertical_sync",
    "show_frame_rate",
    "renderer_mode",
    "renderer_strategy",
    "gpu_mode",
    "gpu_model.custom",
    "force_discrete_graphics",
    "performance_mode",
    "performance_cpu.custom",
    "performance_mem.custom",
)

# Perubahan pada key ini butuh device dimatikan / restart.
RESTART_KEYS: frozenset[str] = frozenset(
    {
        "resolution_mode",
        "resolution_width.custom",
        "resolution_height.custom",
        "resolution_dpi.custom",
        "renderer_mode",
        "renderer_strategy",
        "gpu_mode",
        "gpu_model.custom",
        "force_discrete_graphics",
        "performance_mode",
        "performance_cpu.custom",
        "performance_mem.custom",
    }
)

LABELS: dict[str, str] = {
    "resolution_mode": "Mode resolusi",
    "resolution_width.custom": "Lebar layar",
    "resolution_height.custom": "Tinggi layar",
    "resolution_dpi.custom": "DPI",
    "max_frame_rate": "FPS maksimum",
    "dynamic_adjust_frame_rate": "Dynamic FPS",
    "dynamic_low_frame_rate_limit": "Batas FPS terendah",
    "vertical_sync": "Vertical sync",
    "show_frame_rate": "Tampilkan FPS",
    "renderer_mode": "Renderer",
    "renderer_strategy": "Video memory",
    "gpu_mode": "GPU model",
    "gpu_model.custom": "GPU model custom",
    "force_discrete_graphics": "GPU dedicated",
    "performance_mode": "Mode performa",
    "performance_cpu.custom": "CPU core",
    "performance_mem.custom": "RAM",
}

RESOLUTION_MODE_NAMES = {
    "phone": "Phone",
    "tablet": "Tablet",
    "widescreen": "Widescreen",
}

RENDERER_NAMES = {"dx": "DirectX", "vk": "Vulkan"}
RENDERER_STRATEGY_NAMES = {
    "auto": "Auto",
    "perf": "Performa lebih baik",
    "dis": "Tampilan lebih baik",
}
GPU_MODE_NAMES = {
    "low": "Low",
    "middle": "Middle",
    "high": "High",
    "custom": "Custom",
}
PERFORMANCE_MODE_NAMES = {
    "low": "Low (hemat)",
    "middle": "Middle (seimbang)",
    "high": "High (performa)",
    "custom": "Custom",
}


def parse_number_list(raw: str) -> list[float]:
    """Ambil angka dari string seperti '[1,2,3](best=4)'."""
    match = re.search(r"\[(.*?)\]", raw or "")
    if not match:
        return []
    values: list[float] = []
    for part in match.group(1).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(float(part))
        except ValueError:
            continue
    return values


def parse_best(raw: str) -> float | None:
    match = re.search(r"best\s*=\s*([0-9.]+)", raw or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def bool_str(value: bool) -> str:
    return "true" if value else "false"


def format_ram(value: str | float) -> str:
    try:
        gb = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{gb:g} GB ({int(round(gb * 1024))} MB)"


def format_number(value: str | float) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def describe_value(key: str, value: str) -> str:
    if key == "renderer_mode":
        return RENDERER_NAMES.get(value, value)
    if key == "renderer_strategy":
        return RENDERER_STRATEGY_NAMES.get(value, value)
    if key == "gpu_mode":
        return GPU_MODE_NAMES.get(value, value)
    if key == "performance_mode":
        return PERFORMANCE_MODE_NAMES.get(value, value)
    if key in {"dynamic_adjust_frame_rate", "vertical_sync", "show_frame_rate",
               "force_discrete_graphics"}:
        return "Aktif" if as_bool(value) else "Nonaktif"
    if key == "performance_mem.custom":
        return format_ram(value)
    if key in {"performance_cpu.custom", "max_frame_rate", "dynamic_low_frame_rate_limit"}:
        return format_number(value)
    if key in {"resolution_width.custom", "resolution_height.custom"}:
        return format_number(value) + " px"
    if key == "resolution_dpi.custom":
        return format_number(value) + " dpi"
    return str(value)


def describe_change(key: str, old: str, new: str) -> str:
    return (
        f"{LABELS.get(key, key)}: "
        f"{describe_value(key, old)} \u2192 {describe_value(key, new)}"
    )
