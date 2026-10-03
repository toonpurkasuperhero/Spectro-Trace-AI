"""
SpectroTrace AI — Central Generative Policy Engine
Defines allow/deny rules, policy matrices, prompt templates, and label constants
for all generative features (Feature A: Remediation, Feature B: Simulation, Feature C: Export Profiles).

Design Principle: POLICY BEFORE PROMPT.
- Default deny.
- Generative outputs NEVER feed back into CV, DSP, vision, or evaluation.
- Every generated asset must carry an in-image label and UI disclaimer.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Tuple, Any

@dataclass(frozen=True)
class GenRule:
    allowed: bool
    prompt: Optional[str] = None          # For gen_remove / gen_replace
    label: str = "AI-generated illustration"
    reason: Optional[str] = None          # Displayed in UI when disabled

# UI banner text shown on all views containing generated content
GENERATIVE_BANNER_TEXT = (
    "AI-generated illustration. Not a measurement, not a repair specification, "
    "not used by the analysis."
)

WATERMARK_TEXT = "AI-generated illustration (display only)"

# -------------------------------------------------------------------------
# Feature A: Remediation Policy Table
# (module, mode, finding_label) -> GenRule
# -------------------------------------------------------------------------
REMEDIATION_POLICY: Dict[Tuple[str, str, str], GenRule] = {
    # Print defect module (Additive Manufacturing)
    ("print", "*", "crack"):                GenRule(True, prompt="the crack", label="Illustrative: defect removed"),
    ("print", "*", "void"):                 GenRule(True, prompt="the void", label="Illustrative: defect removed"),
    ("print", "*", "under_extrusion_void"): GenRule(True, prompt="under-extrusion void", label="Illustrative: void removed"),
    ("print", "*", "stringing"):            GenRule(True, prompt="thin plastic strings", label="Illustrative: defect removed"),
    ("print", "*", "under_extrusion"):      GenRule(True, prompt="under-extruded area", label="Illustrative: defect removed"),
    ("print", "*", "debris"):               GenRule(True, prompt="surface debris", label="Illustrative: debris removed"),
    ("print", "*", "surface_deviation"):    GenRule(True, prompt="surface deviation", label="Illustrative: defect removed"),

    # Specimen module — Materials Mode (Illustrative only)
    ("specimen", "materials", "micro_crack"):       GenRule(True, prompt="the micro crack", label="Illustrative: defect removed"),
    ("specimen", "materials", "crack"):             GenRule(True, prompt="the crack", label="Illustrative: defect removed"),
    ("specimen", "materials", "pitting_corrosion"): GenRule(True, prompt="the corrosion pits", label="Illustrative: pits removed"),
    ("specimen", "materials", "void"):              GenRule(True, prompt="the material void", label="Illustrative: void removed"),
    ("specimen", "materials", "micro_defect"):      GenRule(True, prompt="the micro defect", label="Illustrative: defect removed"),
    ("specimen", "materials", "surface_crack"):     GenRule(True, prompt="the surface crack", label="Illustrative: defect removed"),
    ("specimen", "materials", "inclusion"):         GenRule(True, prompt="the material inclusion", label="Illustrative: inclusion removed"),
    ("specimen", "materials", "delamination"):      GenRule(True, prompt="the delamination", label="Illustrative: delamination removed"),
    ("specimen", "materials", "*"):                 GenRule(True, prompt="the defect", label="Illustrative: defect removed"),

    # Specimen module — Wildcard Mode (supports general specimen materials analysis)
    ("specimen", "*", "micro_crack"):               GenRule(True, prompt="the micro crack", label="Illustrative: defect removed"),
    ("specimen", "*", "crack"):                     GenRule(True, prompt="the crack", label="Illustrative: defect removed"),
    ("specimen", "*", "pitting_corrosion"):         GenRule(True, prompt="the corrosion pits", label="Illustrative: pits removed"),
    ("specimen", "*", "void"):                      GenRule(True, prompt="the material void", label="Illustrative: void removed"),
    ("specimen", "*", "micro_defect"):              GenRule(True, prompt="the micro defect", label="Illustrative: defect removed"),
    ("specimen", "*", "surface_crack"):             GenRule(True, prompt="the surface crack", label="Illustrative: defect removed"),
    ("specimen", "*", "inclusion"):                 GenRule(True, prompt="the material inclusion", label="Illustrative: inclusion removed"),
    ("specimen", "*", "delamination"):              GenRule(True, prompt="the delamination", label="Illustrative: delamination removed"),
    ("specimen", "*", "*"):                         GenRule(True, prompt="the defect", label="Illustrative: defect removed"),

    # Specimen module — Histology Mode (STRICT: Artifacts only, never tissue candidates)
    ("specimen", "histology", "dust_artifact"):    GenRule(True, prompt="dust particles", label="Artifact cleanup (display only)"),
    ("specimen", "histology", "stain_artifact"):   GenRule(True, prompt="stain artifact", label="Artifact cleanup (display only)"),
    ("specimen", "histology", "scratch_artifact"): GenRule(True, prompt="glass scratch", label="Artifact cleanup (display only)"),
    ("specimen", "histology", "bubble_artifact"):  GenRule(True, prompt="coverslip air bubble", label="Artifact cleanup (display only)"),

    # HARD POLICY: Never remediate biological cellular/tissue findings
    ("specimen", "histology", "tissue_fold"):      GenRule(False, reason="Tissue findings are biological candidates and are never regenerated"),
    ("specimen", "histology", "dense_cellularity"):GenRule(False, reason="Tissue findings are biological candidates and are never regenerated"),
    ("specimen", "histology", "irregular_nuclei"): GenRule(False, reason="Tissue findings are biological candidates and are never regenerated"),

    # Thermal module: NEVER edit radiometric measurements or hot/cold spots
    ("thermal", "*", "*"):  GenRule(False, reason="Thermal measurements cannot be edited: removing anomalies misrepresents heat transfer physics"),

    # Audio module: NEVER edit spectrograms
    ("audio", "*", "*"):    GenRule(False, reason="Generative removal is not applicable to acoustic spectrograms"),
}

def rule_for_remediation(module: str, mode: str = "*", label: str = "*") -> GenRule:
    """
    Evaluates remediation policy with hierarchical lookup:
    1. Exact match (module, mode, label)
    2. Wildcard mode (module, "*", label)
    3. Wildcard label (module, mode, "*")
    4. Wildcard both (module, "*", "*")
    5. Default deny
    """
    # Strict safeguard: biological cellular/tissue findings are never remediated under any mode
    if module == "specimen" and label in ("tissue_fold", "dense_cellularity", "irregular_nuclei"):
        return GenRule(False, reason="Tissue findings are biological candidates and are never regenerated")

    key_exact = (module, mode, label)
    if key_exact in REMEDIATION_POLICY:
        return REMEDIATION_POLICY[key_exact]

    key_wild_mode = (module, "*", label)
    if key_wild_mode in REMEDIATION_POLICY:
        return REMEDIATION_POLICY[key_wild_mode]

    # Substring match on known label terms for module
    if label != "*":
        for (m, md, lbl), rule in REMEDIATION_POLICY.items():
            if m == module and (md == mode or md == "*") and lbl != "*":
                if lbl in label or label in lbl:
                    return rule

    key_wild_label = (module, mode, "*")
    if key_wild_label in REMEDIATION_POLICY:
        return REMEDIATION_POLICY[key_wild_label]

    key_wild_both = (module, "*", "*")
    if key_wild_both in REMEDIATION_POLICY:
        return REMEDIATION_POLICY[key_wild_both]

    # Default deny
    return GenRule(
        allowed=False,
        reason=f"Generative remediation is not permitted for module '{module}' with label '{label}'"
    )


# -------------------------------------------------------------------------
# Feature C: Export GenFill Policy
# -------------------------------------------------------------------------
def policy_allows_genfill(module: str, mode: str = "*") -> Tuple[bool, Optional[str]]:
    """
    Determines whether generative outpainting (b_gen_fill) is permissible.
    """
    m = module.lower()
    if m == "print":
        return True, None
    elif m == "thermal":
        if mode == "radiometric":
            return False, "Generative fill is only allowed on visible-light photographs, not radiometric thermograms"
        return True, None
    elif m == "specimen":
        if mode in ("histology", "histopathology_screening"):
            return False, "Generative fill is strictly prohibited on histology specimen images"
        return True, None
    elif m == "audio":
        return False, "Generative fill is not permitted on audio spectrograms"
    return False, f"Generative fill is disabled by policy for module '{module}'"



# -------------------------------------------------------------------------
# Feature B: Simulation Lab Scenarios & Allowlist
# -------------------------------------------------------------------------
SIMULATION_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "corrosion": {
        "label": "Surface Corrosion",
        "description": "Oxidation and pitting on metal surfaces under industrial exposure",
        "modules": ["print", "specimen", "specimen:materials", "thermal"],
        "template": "{subject} showing {severity_word} rust and oxidation on metal surfaces, realistic industrial lighting"
    },
    "humidity": {
        "label": "High Humidity Damage",
        "description": "Moisture condensation, water staining, and damp environment degradation",
        "modules": ["thermal", "print", "specimen", "specimen:materials"],
        "template": "{subject} with {severity_word} moisture staining and condensation"
    },
    "thermal_cycling": {
        "label": "Thermal Cycling Wear",
        "description": "Micro-cracking and material deformation from repeated thermal expansion",
        "modules": ["print", "specimen", "specimen:materials", "thermal"],
        "template": "{subject} with {severity_word} warping and micro-cracking from heat cycles"
    },
    "weathering": {
        "label": "Environmental Weathering",
        "description": "Sun, rain, and age exposure on outdoor structures or facades",
        "modules": ["thermal", "print", "specimen", "specimen:materials"],
        "template": "{subject} after years of weathering with {severity_word} paint fade and surface wear"
    },
    "micro_fracture": {
        "label": "Micro-Fracture Propagation",
        "description": "Simulation of micro-crack growth under cyclical mechanical stress",
        "modules": ["specimen", "specimen:materials", "print", "thermal"],
        "template": "{subject} with {severity_word} micro-fracture propagation across the surface"
    },
    "delamination": {
        "label": "Layer Delamination",
        "description": "Separation of material layers due to adhesion failure",
        "modules": ["print", "specimen", "specimen:materials", "thermal"],
        "template": "{subject} showing {severity_word} delamination and layer separation"
    },
}

SEVERITY_WORDS: Dict[int, str] = {
    1: "faint",
    2: "light",
    3: "moderate",
    4: "heavy",
    5: "severe"
}

def policy_allows_simulation(module: str, mode: str = "*", scenario: str = "*") -> Tuple[bool, Optional[str]]:
    """
    Validates if a simulation scenario is permitted for a given module and mode.
    """
    m = module.lower()
    if m == "audio":
        return False, "Simulation Lab is not available for audio spectrograms"
    if m == "specimen" and mode in ("histology", "histopathology_screening"):
        return False, "Simulation Lab is strictly prohibited on medical histology specimens"
    if m == "thermal" and mode == "radiometric":
        return False, "Simulation is only permitted on the visible-light photograph, never on radiometric thermograms"


    if scenario != "*":
        sc_info = SIMULATION_SCENARIOS.get(scenario)
        if not sc_info:
            return False, f"Unknown simulation scenario '{scenario}'"

        # Check module compatibility
        allowed_mods = sc_info.get("modules", [])
        match = False
        for target in allowed_mods:
            t_base = target.split(":")[0]
            if target in (m, "*", f"{m}:{mode}") or t_base == m:
                match = True
                break
            if mode == "*" and t_base == m:
                match = True
                break
        if not match:
            return False, f"Scenario '{scenario}' is not applicable to {module} ({mode})"

    return True, None

