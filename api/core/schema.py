from typing import List, Dict, Any, Optional, Tuple, Callable
from pydantic import BaseModel, Field

class CalibrationAxis(BaseModel):
    unit: str
    min: float
    max: float
    scale: Optional[str] = "linear"  # "linear" | "mel" | "log"

class ValueMap(BaseModel):
    unit: str
    min: float
    max: float
    source: str = "radiometric"  # "radiometric" | "approximate"

class Calibration(BaseModel):
    kind: str  # "thermal" | "spectrogram" | "slide" | "layer"
    width_px: int
    height_px: int
    axes: Dict[str, CalibrationAxis] = Field(default_factory=dict)
    value_map: Optional[ValueMap] = None
    encoding: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)

def make_json_serializable(val: Any) -> Any:
    if hasattr(val, "item"):
        return val.item()
    if isinstance(val, dict):
        return {k: make_json_serializable(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [make_json_serializable(x) for x in val]
    return val

class VisionResult(BaseModel):
    classification: str
    explanation: str
    confidence: float = 1.0

class Finding(BaseModel):
    id: str
    label: str
    short_label: Optional[str] = None
    region_px: Tuple[int, int, int, int]  # (x, y, w, h)
    region_physical: Dict[str, Any] = Field(default_factory=dict)
    measurements: Dict[str, Any] = Field(default_factory=dict)
    source: str = "cv"  # "cv" | "dsp"
    vision: Optional[VisionResult] = None
    severity: float = 0.0  # 0.0 to 1.0
    risk_level: str = "low"  # "low" | "medium" | "high"
    needs_review: bool = False

    def model_post_init(self, __context):
        if not self.short_label:
            self.short_label = self.label[:16]
        self.measurements = make_json_serializable(self.measurements)
        self.region_physical = make_json_serializable(self.region_physical)
        if isinstance(self.region_px, (list, tuple)):
            self.region_px = tuple(int(x) for x in self.region_px)

class GenerativeStep(BaseModel):
    step: str
    purpose: str = "display only"

class Provenance(BaseModel):
    pipeline_version: str = "1.0.0"
    deterministic_steps: List[str] = Field(default_factory=list)
    generative_steps: List[GenerativeStep] = Field(default_factory=list)
    vision: Dict[str, Any] = Field(default_factory=dict)
    input_hash: str = ""

class JobResult(BaseModel):
    job_id: str
    module: str
    status: str  # "queued" | "encoding" | "measuring" | "vision" | "publishing" | "done" | "done_partial" | "done_no_vision" | "failed"
    stage: str = "queued"
    error: Optional[str] = None
    assets: Dict[str, Any] = Field(default_factory=dict)
    calibration: Optional[Calibration] = None
    findings: List[Finding] = Field(default_factory=list)
    summary: str = ""
    risk_level: str = "low"
    risk_score: int = 0
    review_state: str = "pending"
    provenance: Optional[Provenance] = None

class ModuleConfig(BaseModel):
    id: str  # "print" | "thermal" | "specimen" | "audio"
    name: str
    upload_preset: str
    resource_type: str = "image"  # "image" | "video" | "raw"
    tag_prefix: str
    vision_prompt: str = ""
    display_views: List[str] = Field(default_factory=list)
    genfeatures: Dict[str, Any] = Field(default_factory=dict)
