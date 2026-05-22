from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProductFamily(str, Enum):
    TILE_ADHESIVE = "tile_adhesive"
    SPECIALTY_ADHESIVE = "specialty_adhesive"
    STONE_ADHESIVE = "stone_adhesive"
    GROUT = "grout"
    WATERPROOFING = "waterproofing"
    SURFACE_PREP = "surface_prep"
    STONE_CARE = "stone_care"
    CLEANING = "cleaning"
    SCREED = "screed"
    SOUND_CONTROL = "sound_control"
    CEMENT_ADDITIVE = "cement_additive"
    THREE_D_MORTAR = "3d_mortar"


class TechnicalSpecs(BaseModel):
    open_time: Optional[str] = None
    pot_life: Optional[str] = None
    coverage_rate: Optional[str] = None
    compressive_strength: Optional[str] = None
    shear_bond_strength: Optional[str] = None
    application_thickness: Optional[str] = None
    cure_time: Optional[str] = None
    mixing_ratio: Optional[str] = None
    temperature_range: Optional[str] = None


class Packaging(BaseModel):
    sizes: list[str] = Field(default_factory=list)
    shelf_life: Optional[str] = None


class ProductRecord(BaseModel):
    sku: Optional[str] = None
    product_name: str
    product_family: ProductFamily
    description: Optional[str] = None
    technical_specs: TechnicalSpecs = Field(default_factory=TechnicalSpecs)
    grade_classification: Optional[str] = None
    substrate_compatibility: list[str] = Field(default_factory=list)
    tile_compatibility: list[str] = Field(default_factory=list)
    recommended_use_cases: list[str] = Field(default_factory=list)
    packaging: Packaging = Field(default_factory=Packaging)
    source_urls: list[str] = Field(default_factory=list)
    extraction_confidence: float = 0.0
    needs_human_review: bool = False
    version: int = 1
    extracted_at: str = ""
