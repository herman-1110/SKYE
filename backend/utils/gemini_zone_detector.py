import io
import json
import logging

import httpx
import PIL.Image
import requests

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from fastapi import HTTPException

from config.settings import settings

logger = logging.getLogger(__name__)

RISK_COLOURS = {
    "high":     "#fca5a533",  # light red   (Tailwind red-300 with alpha)
    "moderate": "#fde68a33",  # light yellow (Tailwind yellow-200 with alpha)
    "low":      "#bbf7d033",  # light green  (Tailwind green-200 with alpha)
}


def _compress_for_gemini(img: PIL.Image.Image) -> tuple[bytes, int, int]:
    """Resize to max 800 px wide and encode as JPEG. Returns (bytes, width_px, height_px)."""
    max_width = 800
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), PIL.Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue(), img.width, img.height


def _apply_risk_colours(zones: list[dict]) -> None:
    """Map risk_level to color and is_high_risk for each zone."""
    for zone in zones:
        risk = zone.get("risk_level", "moderate").lower()
        if risk not in RISK_COLOURS:
            risk = "moderate"
        zone["risk_level"] = risk
        zone["color"] = RISK_COLOURS[risk]
        zone["is_high_risk"] = (risk == "high")


ZONE_DETECTION_PROMPT = """
Analyse this industrial facility floor plan image.

Identify all distinct zones or areas visible in the floor plan.

The coordinate origin (0.0, 0.0) is the TOP-LEFT corner.
(1.0, 1.0) is the BOTTOM-RIGHT corner.
Express ALL coordinates as fractions of the image dimensions (0.0 to 1.0).

For each zone, return:
- name: descriptive zone name
- risk_level: one of "high", "moderate", or "low"
  - high: machinery areas, chemical storage, electrical rooms, loading docks, forklift paths
  - moderate: corridors, stairwells, storage rooms, server rooms
  - low: offices, reception, break rooms, toilets
- x_min, x_max, y_min, y_max: bounding box as percentage (0.0 to 1.0) of image dimensions
- reasoning: one sentence explaining the risk classification

Return ONLY a valid JSON array. No markdown, no preamble.

Example:
[
  {"name": "Forklift Bay", "risk_level": "high", "x_min": 0.1, "x_max": 0.4, "y_min": 0.2, "y_max": 0.6, "reasoning": "Active forklift movement zone with blind corners."},
  {"name": "Office Area", "risk_level": "low", "x_min": 0.6, "x_max": 0.9, "y_min": 0.1, "y_max": 0.4, "reasoning": "Administrative area with no heavy machinery."}
]
"""


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
    image = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    # The calibration scale was measured on the original image. After resizing,
    # the compressed image has fewer pixels per metre — adjust accordingly.
    compression_ratio = img_width_px / orig.width
    compressed_scale = scale_pixels_per_meter * compression_ratio
    real_width_m = img_width_px / compressed_scale
    real_height_m = img_height_px / compressed_scale

    logger.info(
        "Compressed image to %dx%d px (%.1f KB), compressed scale=%.2f px/m, real size=%.1fm x %.1fm",
        img_width_px, img_height_px, len(image_bytes) / 1024, compressed_scale, real_width_m, real_height_m,
    )

    prompt = f"The image is {img_width_px} x {img_height_px} pixels.\n" + ZONE_DETECTION_PROMPT

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    try:
        result = client.models.generate_content(
            model=settings.LLM_MODEL_NAME,
            contents=[image, prompt],
            # timeout is milliseconds here (was seconds under the old SDK's
            # request_options). 504/DEADLINE_EXCEEDED responses land as
            # ServerError below; a client-side timeout with no response at
            # all raises httpx.TimeoutException directly instead (caught
            # separately — the new SDK doesn't wrap it into ServerError).
            # No tools passed, so automatic function calling is a no-op —
            # disabled to silence the SDK's per-call "AFC is enabled..."
            # log noise, not a behaviour change.
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=120_000),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except httpx.TimeoutException:
        logger.warning("Gemini deadline exceeded for image: %s", image_url)
        raise HTTPException(status_code=504, detail="AI detection timed out. Please try again.")
    except ServerError as e:
        if e.code == 504:
            logger.warning("Gemini deadline exceeded for image: %s", image_url)
            raise HTTPException(status_code=504, detail="AI detection timed out. Please try again.")
        logger.exception("Gemini generate_content failed")
        raise HTTPException(status_code=500, detail=f"AI zone detection failed: {e}")
    except ClientError as e:
        # RESOURCE_EXHAUSTED (quota) comes back as HTTP 429, a 4xx — still
        # ClientError under the new SDK's code<500 split, unlike the old
        # SDK's distinct ResourceExhausted exception type.
        if e.code == 429:
            logger.warning("Gemini quota exhausted: %s", e)
            raise HTTPException(status_code=503, detail="AI service quota exceeded — try again later.")
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
    logger.info("Parsed zones (raw percentages): %s", json.dumps(zones, indent=2))

    # Convert 0.0–1.0 fractions to metres
    for zone in zones:
        zone["x_min"] = float(zone.get("x_min", 0.0)) * real_width_m
        zone["x_max"] = float(zone.get("x_max", 1.0)) * real_width_m
        zone["y_min"] = float(zone.get("y_min", 0.0)) * real_height_m
        zone["y_max"] = float(zone.get("y_max", 1.0)) * real_height_m
        logger.info(
            "Converted zone '%s': (%.1f,%.1f) → (%.1f,%.1f) metres",
            zone.get("name", "?"), zone["x_min"], zone["y_min"], zone["x_max"], zone["y_max"],
        )

    _apply_risk_colours(zones)

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
        zone.setdefault("risk_level", "moderate")
        zone.setdefault("color", RISK_COLOURS["moderate"])

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
