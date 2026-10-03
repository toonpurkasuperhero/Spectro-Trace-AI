import pytest
from api.core.schema import Calibration, CalibrationAxis
from api.core.calibration import pixel_to_physical, physical_to_pixel

def test_linear_calibration_roundtrip():
    cal = Calibration(
        kind="slide",
        width_px=1000,
        height_px=1000,
        axes={
            "x": CalibrationAxis(unit="um", min=0.0, max=500.0, scale="linear"),
            "y": CalibrationAxis(unit="um", min=0.0, max=500.0, scale="linear")
        }
    )

    orig_px = (200, 300, 100, 150)
    phys = pixel_to_physical(cal, orig_px)
    
    assert phys["x"] == [100.0, 150.0]
    # Check that Y was converted
    assert "y" in phys

    # Round trip
    recovered_px = physical_to_pixel(cal, tuple(phys["x"]), tuple(phys["y"]))
    assert abs(recovered_px[0] - orig_px[0]) <= 1
    assert abs(recovered_px[1] - orig_px[1]) <= 1
    assert abs(recovered_px[2] - orig_px[2]) <= 1
    assert abs(recovered_px[3] - orig_px[3]) <= 1

def test_spectrogram_mel_calibration():
    cal = Calibration(
        kind="spectrogram",
        width_px=800,
        height_px=400,
        axes={
            "x": CalibrationAxis(unit="s", min=0.0, max=10.0, scale="linear"),
            "y": CalibrationAxis(unit="Hz", min=0.0, max=8000.0, scale="mel")
        }
    )

    px_box = (100, 100, 200, 50)
    phys = pixel_to_physical(cal, px_box)

    assert phys["x"] == [1.25, 3.75]
    assert phys["x_unit"] == "s"
    assert phys["y_unit"] == "Hz"
    assert phys["y"][0] < phys["y"][1]  # Lower Hz < Upper Hz

    # Round trip
    recovered_px = physical_to_pixel(cal, tuple(phys["x"]), tuple(phys["y"]))
    assert abs(recovered_px[0] - px_box[0]) <= 2
    assert abs(recovered_px[1] - px_box[1]) <= 2
