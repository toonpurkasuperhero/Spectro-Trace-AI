import pytest
from api.core.schema import Finding, Calibration
from api.core.annotate import build_annotation_transform

def test_annotation_transform_clamping_and_formatting():
    cal = Calibration(
        kind="thermal",
        width_px=640,
        height_px=480
    )

    findings = [
        Finding(
            id="f1",
            label="window_frame_leak",
            short_label="Leak 74C",
            region_px=(50, 60, 100, 80),
            risk_level="high"
        ),
        # Test finding exceeding bounds to check clamping
        Finding(
            id="f2",
            label="out_of_bounds",
            short_label="OOB",
            region_px=(600, 450, 100, 100),
            risk_level="medium"
        )
    ]

    transforms = build_annotation_transform(findings, cal, opacity=45)
    
    # Each finding generates 4 transform steps (overlay rect, apply rect, overlay text, apply text)
    assert len(transforms) == 8

    # Finding 1 rect
    f1_rect = transforms[0]
    assert f1_rect["width"] == 100
    assert f1_rect["height"] == 80
    assert f1_rect["color"] == "red"
    assert f1_rect["opacity"] == 45

    f1_rect_apply = transforms[1]
    assert f1_rect_apply["x"] == 50
    assert f1_rect_apply["y"] == 60

    # Finding 2 rect clamped
    f2_rect = transforms[4]
    assert f2_rect["width"] == 40  # 640 - 600
    assert f2_rect["height"] == 30  # 480 - 450
    assert f2_rect["color"] == "orange"
