from __future__ import annotations

from functools import lru_cache
import ast
from pathlib import Path

import streamlit as st

from src.ui.app_css import APP_CSS

_DEFAULTS = {
    "brand_hue": 14,
    "accent_hue": 221,
    "data_hue": 217,
    "energy_hue": 38,
    "bg_lightness": 99,
    "glass_opacity": 0.92,
    "shape_corner_px": 10,
    "motion_base_ms": 50,
    "font_family": "Manrope",
    "density": "compact",
}


def _coerce_value(raw_value: str) -> object:
    value = raw_value.split("#", 1)[0].strip()
    if not value:
        return ""
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value


def _load_theme_config() -> dict[str, object]:
    path = Path("theme.config.toml")
    if not path.exists():
        return {}

    data: dict[str, object] = {}
    in_theme = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_theme = line == "[theme]"
            continue
        if not in_theme or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = _coerce_value(value)
    return data


@lru_cache(maxsize=1)
def tokens() -> dict[str, object]:
    config = dict(_DEFAULTS)
    config.update(_load_theme_config())
    neutral_hue = 222
    motion_base = int(config["motion_base_ms"])
    return {
        "bg": f"hsl({neutral_hue}, 30%, {config['bg_lightness']}%)",
        "surface": f"hsla(0, 0%, 100%, {config['glass_opacity']})",
        "surface_hi": f"hsl({neutral_hue}, 34%, 95%)",
        "outline": f"hsl({neutral_hue}, 24%, 87%)",
        "accent": f"hsl({config['brand_hue']}, 98%, 58%)",
        "energy": f"hsl({config['energy_hue']}, 92%, 54%)",
        "interactive": f"hsl({config['accent_hue']}, 78%, 53%)",
        "info": f"hsl({config['data_hue']}, 84%, 55%)",
        "positive": "hsl(142, 68%, 38%)",
        "warn": "hsl(33, 89%, 46%)",
        "text": "hsl(222, 47%, 11%)",
        "muted": "hsl(218, 16%, 41%)",
        "radius": f"{config['shape_corner_px']}px",
        "radius_lg": f"{int(config['shape_corner_px']) * 2}px",
        "ease_standard": "cubic-bezier(0.2, 0, 0, 1)",
        "ease_emphatic": "cubic-bezier(0.05, 0.7, 0.1, 1)",
        "dur_short": f"{motion_base * 4}ms",
        "dur_medium": f"{motion_base * 6}ms",
        "dur_long": f"{motion_base * 10}ms",
        "font": str(config["font_family"]),
        "density": str(config["density"]),
    }


def emit_css(theme_tokens: dict[str, object] | None = None) -> str:
    active_tokens = theme_tokens or tokens()
    pairs = {
        "--db-bg": active_tokens["bg"],
        "--db-surface": active_tokens["surface"],
        "--db-surface-hi": active_tokens["surface_hi"],
        "--db-outline": active_tokens["outline"],
        "--db-accent": active_tokens["accent"],
        "--db-energy": active_tokens["energy"],
        "--db-interactive": active_tokens["interactive"],
        "--db-info": active_tokens["info"],
        "--db-positive": active_tokens["positive"],
        "--db-warn": active_tokens["warn"],
        "--db-text": active_tokens["text"],
        "--db-muted": active_tokens["muted"],
        "--db-radius": active_tokens["radius"],
        "--db-radius-lg": active_tokens["radius_lg"],
        "--db-ease-standard": active_tokens["ease_standard"],
        "--db-ease-emphatic": active_tokens["ease_emphatic"],
        "--db-dur-short": active_tokens["dur_short"],
        "--db-dur-medium": active_tokens["dur_medium"],
        "--db-dur-long": active_tokens["dur_long"],
        "--db-font": f"'{active_tokens['font']}', sans-serif",
    }
    body = "\n".join(f"  {key}: {value};" for key, value in pairs.items())
    return f":root {{\n{body}\n}}"


def inject_theme() -> None:
    st.markdown(f"<style>{emit_css()}\n{APP_CSS}</style>", unsafe_allow_html=True)

