import math
from typing import Dict, Any, Tuple, Optional
from api.core.schema import Calibration, CalibrationAxis

def hz_to_mel(hz: float) -> float:
    return 2595.0 * math.log10(1.0 + hz / 700.0)

def mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

def pixel_to_physical(
    cal: Calibration,
    region_px: Tuple[int, int, int, int]
) -> Dict[str, Any]:
    """
    Maps bounding box (x, y, w, h) in pixels to physical coordinates.
    """
    x, y, w, h = region_px
    res = {}

    # Map X-axis
    if "x" in cal.axes:
        ax = cal.axes["x"]
        if cal.width_px > 0:
            scale_factor = (ax.max - ax.min) / cal.width_px
            min_val = ax.min + x * scale_factor
            max_val = ax.min + (x + w) * scale_factor
            res["x"] = [round(min_val, 4), round(max_val, 4)]
            res["x_unit"] = ax.unit

    # Map Y-axis (image origin is top-left, so higher Y px is lower frequency/spatial height)
    if "y" in cal.axes:
        ay = cal.axes["y"]
        if cal.height_px > 0:
            if ay.scale == "mel":
                mel_min = hz_to_mel(ay.min)
                mel_max = hz_to_mel(ay.max)
                mel_span = mel_max - mel_min
                # Invert y: y=0 is highest frequency (mel_max)
                mel_top = mel_max - (y / cal.height_px) * mel_span
                mel_bot = mel_max - ((y + h) / cal.height_px) * mel_span
                hz_bot = mel_to_hz(min(mel_top, mel_bot))
                hz_top = mel_to_hz(max(mel_top, mel_bot))
                res["y"] = [round(hz_bot, 2), round(hz_top, 2)]
            else:
                scale_factor = (ay.max - ay.min) / cal.height_px
                # Inverted Y convention
                y_max_val = ay.max - (y * scale_factor)
                y_min_val = ay.max - ((y + h) * scale_factor)
                res["y"] = [round(min(y_min_val, y_max_val), 4), round(max(y_min_val, y_max_val), 4)]
            res["y_unit"] = ay.unit

    return res

def physical_to_pixel(
    cal: Calibration,
    physical_x: Optional[Tuple[float, float]] = None,
    physical_y: Optional[Tuple[float, float]] = None
) -> Tuple[int, int, int, int]:
    """
    Maps physical bounds to pixel coordinates (x, y, w, h).
    """
    x, y, w, h = 0, 0, cal.width_px, cal.height_px

    if physical_x and "x" in cal.axes and cal.width_px > 0:
        ax = cal.axes["x"]
        span = ax.max - ax.min
        if span > 0:
            x = int(((physical_x[0] - ax.min) / span) * cal.width_px)
            w = int(((physical_x[1] - physical_x[0]) / span) * cal.width_px)

    if physical_y and "y" in cal.axes and cal.height_px > 0:
        ay = cal.axes["y"]
        if ay.scale == "mel":
            mel_min = hz_to_mel(ay.min)
            mel_max = hz_to_mel(ay.max)
            span = mel_max - mel_min
            if span > 0:
                mel_low = hz_to_mel(physical_y[0])
                mel_high = hz_to_mel(physical_y[1])
                # Invert: mel_max is y=0
                y1 = int(((mel_max - mel_high) / span) * cal.height_px)
                y2 = int(((mel_max - mel_low) / span) * cal.height_px)
                y = min(y1, y2)
                h = max(1, abs(y2 - y1))
        else:
            span = ay.max - ay.min
            if span > 0:
                y1 = int(((ay.max - physical_y[1]) / span) * cal.height_px)
                y2 = int(((ay.max - physical_y[0]) / span) * cal.height_px)
                y = min(y1, y2)
                h = max(1, abs(y2 - y1))

    # Clamp to dimensions
    x = max(0, min(x, cal.width_px - 1))
    y = max(0, min(y, cal.height_px - 1))
    w = max(1, min(w, cal.width_px - x))
    h = max(1, min(h, cal.height_px - y))

    return (x, y, w, h)
