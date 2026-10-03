from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_URL: Optional[str] = None

    # Application
    ENV: str = "dev"
    DEMO_MODE: bool = False
    API_BASE: str = "http://localhost:8000"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Database
    DATABASE_URL: str = "sqlite:///./spectrotrace.db"

    # Budget Caps
    MAX_GENERATIVE_CALLS_PER_DAY: int = 50
    MAX_VISION_CALLS_PER_DAY: int = 100
    MAX_IMAGEGEN_CALLS_PER_DAY: int = 20
    MAX_GENFILL_CALLS_PER_DAY: int = 40
    MAX_GENREMOVE_CALLS_PER_DAY: int = 40

    # Generative Features
    GEN_FEATURES_ENABLED: bool = True
    IMAGE_GEN_BASE: str = ""
    SIM_ALLOWED_FAMILIES: str = "flux,auto"
    SIM_DEFAULT_TIER: str = "economy"
    SIM_ALLOW_PREMIUM: bool = False

    # Vision Provider
    VISION_PROVIDER: str = "fallback"
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-1.5-flash"

    # Presets
    CLD_PRESET_PRINT: str = "st_print"
    CLD_PRESET_THERMAL: str = "st_thermal"
    CLD_PRESET_SPECIMEN: str = "st_specimen"
    CLD_PRESET_AUDIO: str = "st_audio"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
