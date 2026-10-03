import pytest
from api.core.gen_policy import (
    rule_for_remediation,
    policy_allows_genfill,
    policy_allows_simulation,
    GENERATIVE_BANNER_TEXT,
    WATERMARK_TEXT
)

def test_remediation_policy_print_module():
    # Cracks, voids, and stringing on print module are allowed
    r_crack = rule_for_remediation("print", "*", "crack")
    assert r_crack.allowed is True
    assert "crack" in r_crack.prompt

    r_void = rule_for_remediation("print", "*", "void")
    assert r_void.allowed is True

    r_stringing = rule_for_remediation("print", "*", "stringing")
    assert r_stringing.allowed is True

def test_remediation_policy_thermal_and_audio_blocked():
    # Thermal measurements cannot be altered
    r_thermal = rule_for_remediation("thermal", "*", "hotspot")
    assert r_thermal.allowed is False
    assert "Thermal measurements cannot be edited" in r_thermal.reason

    # Audio spectrograms cannot be altered
    r_audio = rule_for_remediation("audio", "*", "hum")
    assert r_audio.allowed is False
    assert "not applicable" in r_audio.reason.lower()

def test_remediation_policy_histology_safeguards():
    # Artifacts like dust, scratches, and stains are permitted for cleanup
    r_dust = rule_for_remediation("specimen", "histology", "dust_artifact")
    assert r_dust.allowed is True
    assert "Artifact cleanup" in r_dust.label

    # Biological tissue candidates are STRICTLY PROHIBITED
    r_cell = rule_for_remediation("specimen", "histology", "dense_cellularity")
    assert r_cell.allowed is False
    assert "Tissue findings are biological candidates" in r_cell.reason

    r_nuclei = rule_for_remediation("specimen", "histology", "irregular_nuclei")
    assert r_nuclei.allowed is False

    r_fold = rule_for_remediation("specimen", "histology", "tissue_fold")
    assert r_fold.allowed is False

def test_remediation_default_deny():
    # Unknown module or label must default to deny
    r_unknown = rule_for_remediation("unknown_mod", "*", "some_defect")
    assert r_unknown.allowed is False

def test_policy_allows_genfill():
    # Print: allowed
    allowed, reason = policy_allows_genfill("print")
    assert allowed is True
    assert reason is None

    # Thermal: visible photo allowed, radiometric render denied
    allowed_vis, _ = policy_allows_genfill("thermal", mode="visible")
    assert allowed_vis is True

    allowed_rad, reason_rad = policy_allows_genfill("thermal", mode="radiometric")
    assert allowed_rad is False
    assert "visible-light photo" in reason_rad

    # Specimen: materials allowed, histology denied
    allowed_mat, _ = policy_allows_genfill("specimen", mode="materials")
    assert allowed_mat is True

    allowed_hist, reason_hist = policy_allows_genfill("specimen", mode="histology")
    assert allowed_hist is False
    assert "prohibited on histology" in reason_hist

    # Audio: denied
    allowed_aud, reason_aud = policy_allows_genfill("audio")
    assert allowed_aud is False
    assert "spectrograms" in reason_aud

def test_policy_allows_simulation():
    # Audio denied
    allowed, reason = policy_allows_simulation("audio")
    assert allowed is False

    # Histology denied
    allowed_hist, reason_hist = policy_allows_simulation("specimen", mode="histology")
    assert allowed_hist is False

    # Print with corrosion scenario allowed
    allowed_print, _ = policy_allows_simulation("print", scenario="corrosion")
    assert allowed_print is True
