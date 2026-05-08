import io
import json
import logging

import PIL.Image
import requests

import google.generativeai as genai
from fastapi import HTTPException
from google.api_core.exceptions import DeadlineExceeded, InvalidArgument, ResourceExhausted

from config.settings import settings

logger = logging.getLogger(__name__)


def _compress_for_gemini(img: PIL.Image.Image) -> tuple[bytes, int, int]:
    """Resize to max 800 px wide and encode as JPEG. Returns (bytes, width_px, height_px)."""
    max_width = 800
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), PIL.Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue(), img.width, img.height


_COLOR_HIGH_RISK = "#ef444433"
_COLOR_NORMAL    = "#3b82f633"
_COLOR_CORRIDOR  = "#22c55e33"
_COLOR_STORAGE   = "#f59e0b33"

_VALID_COLORS = {_COLOR_HIGH_RISK, _COLOR_NORMAL, _COLOR_CORRIDOR, _COLOR_STORAGE}

_STORAGE_KEYWORDS  = ["storage", "warehouse", "stock", "pantry", "laundry", "closet", "utility"]
_CORRIDOR_KEYWORDS = ["corridor", "hallway", "exit", "lobby", "entrance", "aisle", "passage"]


def _apply_fallback_colors(zones: list[dict]) -> None:
    """
    Overwrite missing, empty, or unrecognised color values with a deterministic
    color derived from is_high_risk and zone name keywords.
    """
    for zone in zones:
        color = zone.get("color", "")
        if color in _VALID_COLORS:
            continue
        name = zone.get("name", "").lower()
        if zone.get("is_high_risk"):
            zone["color"] = _COLOR_HIGH_RISK
        elif any(k in name for k in _CORRIDOR_KEYWORDS):
            zone["color"] = _COLOR_CORRIDOR
        elif any(k in name for k in _STORAGE_KEYWORDS):
            zone["color"] = _COLOR_STORAGE
        else:
            zone["color"] = _COLOR_NORMAL


def detect_zones_from_image(image_url: str, scale_pixels_per_meter: float) -> list[dict]:
    """
    Download the floor plan image, ask Gemini Vision to identify zones, and return
    the suggested zone list. Zones are NOT saved — the caller (admin) must confirm.
    """
    logger.info("Starting AI zone detection for image: %s", image_url)

    response = requests.get(image_url, timeout=30)
    response.raise_for_status()

    orig = PIL.Image.open(io.BytesIO(response.content))

    image_bytes, img_width_px, img_height_px = _compress_for_gemini(orig)
    image = {"mime_type": "image/jpeg", "data": image_bytes}

    # The calibration scale was measured on the original image. After resizing,
    # the compressed image has fewer pixels per metre — adjust accordingly so
    # the conversion formula Gemini receives matches what it actually sees.
    compression_ratio = img_width_px / orig.width
    compressed_scale = scale_pixels_per_meter * compression_ratio
    real_width_m = img_width_px / compressed_scale
    real_height_m = img_height_px / compressed_scale

    logger.info(
        "Compressed image to %dx%d px (%.1f KB), compressed scale=%.2f px/m, real size=%.1fm x %.1fm",
        img_width_px, img_height_px, len(image_bytes) / 1024, compressed_scale, real_width_m, real_height_m,
    )

    prompt = f"""Analyse this floor plan image carefully.

Image pixel dimensions: {img_width_px} x {img_height_px} pixels
Scale: {compressed_scale:.2f} pixels per metre
Real-world dimensions:
  Width:  {real_width_m:.1f} metres
  Height: {real_height_m:.1f} metres

The coordinate origin (0, 0) is the TOP-LEFT corner of the image.
X increases to the right. Y increases downward.

To convert a pixel position to metres:
  x_metres = pixel_x / {compressed_scale:.2f}
  y_metres = pixel_y / {compressed_scale:.2f}

Use this conversion to estimate zone boundaries precisely.
First, determine what type of building this is
(e.g. factory, warehouse, office, residential, hospital).
Then identify every distinct room, area, and zone visible.
Name each zone appropriately for the building type you detected.

For industrial/factory buildings use names like:
  Loading Bay, Control Room, Assembly Floor, Forklift Zone,
  Storage Area, Exit Corridor, Warehouse, etc.

For office buildings use names like:
  Meeting Room, Open Office, Reception, Server Room, etc.

For any building type, also identify:
  - High-risk zones (heavy machinery, forklifts, electrical rooms,
    hazardous storage) → is_high_risk: true
  - All other zones → is_high_risk: false

Assign a colour based on zone function:
  High risk zones:    "#ef444433"
  Normal work areas:  "#3b82f633"
  Exit/corridors:     "#22c55e33"
  Storage areas:      "#f59e0b33"

Respond with ONLY a valid JSON array — no explanation, no markdown.

[
  {{
    "name": "Zone Name",
    "x_min": 0.0,
    "x_max": 5.5,
    "y_min": 0.0,
    "y_max": 4.0,
    "is_high_risk": true,
    "color": "#ef444433"
  }}
]
"""

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.LLM_MODEL_NAME)

    try:
        result = model.generate_content(
            [image, prompt],
            request_options={"timeout": 120},
        )
    except DeadlineExceeded:
        logger.warning("Gemini deadline exceeded for image: %s", image_url)
        raise HTTPException(status_code=504, detail="AI detection timed out. Please try again.")
    except ResourceExhausted as e:
        logger.warning("Gemini quota exhausted: %s", e)
        raise HTTPException(status_code=503, detail="AI service quota exceeded — try again later.")
    except InvalidArgument as e:
        logger.warning("Gemini invalid argument: %s", e)
        raise HTTPException(status_code=400, detail=f"AI request rejected: {e}")
    except Exception as e:
        logger.exception("Gemini generate_content failed")
        raise HTTPException(status_code=500, detail=f"AI zone detection failed: {e}")

    raw = result.text.strip()
    # Strip accidental markdown code fences
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]

    zones: list[dict] = json.loads(raw.strip())
    logger.info("Parsed zones: %s", json.dumps(zones, indent=2))

    _apply_fallback_colors(zones)

    valid_zones = []
    for zone in zones:
        if not zone.get("name"):
            logger.warning("Skipping zone with no name: %s", zone)
            continue

        zone.setdefault("x_min", 0.0)
        zone.setdefault("y_min", 0.0)
        zone.setdefault("x_max", real_width_m)
        zone.setdefault("y_max", real_height_m)
        zone.setdefault("is_high_risk", False)
        zone.setdefault("color", "#3b82f633")

        zone["x_min"] = max(0.0, min(float(zone["x_min"]), real_width_m))
        zone["x_max"] = max(0.0, min(float(zone["x_max"]), real_width_m))
        zone["y_min"] = max(0.0, min(float(zone["y_min"]), real_height_m))
        zone["y_max"] = max(0.0, min(float(zone["y_max"]), real_height_m))

        if zone["x_min"] >= zone["x_max"]:
            zone["x_max"] = min(zone["x_min"] + 1.0, real_width_m)
        if zone["y_min"] >= zone["y_max"]:
            zone["y_max"] = min(zone["y_min"] + 1.0, real_height_m)

        valid_zones.append(zone)

    zones = valid_zones
    logger.info("Clamped %d valid zones to bounds (%.1fm x %.1fm)", len(zones), real_width_m, real_height_m)
    logger.info("AI zone detection completed, got %d zones", len(zones))
    return zones
