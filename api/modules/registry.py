from typing import Dict, Optional
from api.core.schema import ModuleConfig
from api.core.config import settings

MODULES: Dict[str, ModuleConfig] = {
    "thermal": ModuleConfig(
        id="thermal",
        name="Thermal Energy Loss & HVAC Leak Radiometry",
        upload_preset=settings.CLD_PRESET_THERMAL,
        resource_type="image",
        tag_prefix="thermal",
        vision_prompt=(
            "You are an industrial thermography and building physics inspector. "
            "For each candidate anomaly region identified by CV, classify the heat loss source "
            "(window_frame_leak | missing_insulation | thermal_bridge | hvac_duct_leak | reflection_artifact | heat_source) "
            "and provide a concise physical explanation."
        ),
        display_views=["raw", "annotated", "clean", "fusion"],
        genfeatures={
            "remediation": {"allowed": False, "reason": "Thermal measurements cannot be edited: removing anomalies misrepresents heat transfer physics"},
            "simulation": {"allowed": True, "target": "visible", "reason": "Permitted on visible photo only"},
            "export_genfill": False
        }
    ),
    "audio": ModuleConfig(
        id="audio",
        name="SpectroTrace AI Forensic Speech & Audio Diagnostics",
        upload_preset=settings.CLD_PRESET_AUDIO,
        resource_type="video",  # Cloudinary classifies audio under video
        tag_prefix="audio",
        vision_prompt=(
            "You are a forensic audio spectrogram examiner. "
            "Examine the spectrogram regions detected by DSP and classify each pattern "
            "(stationary_hum | broadband_noise | clipping | abrupt_splice_like | harmonic_irregularity | normal)."
        ),
        display_views=["raw", "annotated", "clean"],
        genfeatures={
            "remediation": {"allowed": False, "reason": "Generative removal is not applicable to acoustic spectrograms"},
            "simulation": {"allowed": False, "reason": "Simulation Lab is not available for audio spectrograms"},
            "export_genfill": False
        }
    ),
    "print": ModuleConfig(
        id="print",
        name="Micro-Defect & Stress-Map Vision",
        upload_preset=settings.CLD_PRESET_PRINT,
        resource_type="image",
        tag_prefix="print",
        vision_prompt=(
            "Examine additive manufacturing layer camera defects and classify as "
            "(stringing | under-extrusion | warp | crack | debris | false_positive)."
        ),
        display_views=["raw", "annotated", "clean", "deviation_heatmap"],
        genfeatures={
            "remediation": {"allowed": True, "labels": ["crack", "void", "stringing", "under_extrusion", "debris", "surface_deviation"]},
            "simulation": {"allowed": True, "scenarios": ["corrosion", "humidity", "thermal_cycling"]},
            "export_genfill": True
        }
    ),
    "specimen": ModuleConfig(
        id="specimen",
        name="SpecimenTrace-AI Pathology & Material Degradation",
        upload_preset=settings.CLD_PRESET_SPECIMEN,
        resource_type="image",
        tag_prefix="specimen",
        vision_prompt=(
            "Examine microscopic specimen tiles and classify as "
            "(dense_cellularity | irregular_nuclei | tissue_fold | crack | pitting_corrosion | stain_artifact | dust_artifact)."
        ),
        display_views=["raw", "annotated", "clean", "normalized"],
        genfeatures={
            "remediation": {
                "allowed": True,
                "materials": ["crack", "pitting_corrosion", "void"],
                "histology_artifacts_only": ["dust_artifact", "stain_artifact", "scratch_artifact", "bubble_artifact"],
                "histology_tissue_blocked": ["tissue_fold", "dense_cellularity", "irregular_nuclei"]
            },
            "simulation": {"allowed": True, "materials_only": True, "scenarios": ["corrosion"]},
            "export_genfill": False
        }
    )
}

def get_module_config(module_id: str) -> Optional[ModuleConfig]:
    return MODULES.get(module_id)
