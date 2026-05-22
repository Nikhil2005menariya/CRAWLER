# TASK 2 — Catalog Parser (LangGraph-Integrated)

## Objective
Extract structured product records via `parse_node` in the LangGraph pipeline.
Uses Gemini 2.5 Flash as a LangChain tool for structured extraction.

## How it fits in LangGraph

```
parse_node receives IngestionState with crawl_records (only new/modified).
It calls the extract_product_specs tool (Gemini Flash) for each record.
Validates via Pydantic, scores confidence, stores version history.
Outputs products list in IngestionState.
```

## Product Schema (`parser/product_schema.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

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
    sizes: list[str] = []
    shelf_life: Optional[str] = None

class ProductRecord(BaseModel):
    sku: Optional[str] = None
    product_name: str
    product_family: ProductFamily
    description: Optional[str] = None
    technical_specs: TechnicalSpecs = TechnicalSpecs()
    grade_classification: Optional[str] = None
    substrate_compatibility: list[str] = []
    tile_compatibility: list[str] = []
    recommended_use_cases: list[str] = []
    packaging: Packaging = Packaging()
    source_urls: list[str] = []
    extraction_confidence: float = 0.0
    needs_human_review: bool = False
    version: int = 1
    extracted_at: str = ""
```

## LangChain Tool for Extraction (`tools/parse_tools.py`)

```python
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

EXTRACTION_PROMPT = """You are a construction chemicals expert. Extract structured 
product info from this MYK Laticrete content as JSON.

CONTENT:
{content}

Return JSON with: sku, product_name, product_family (one of: tile_adhesive, 
specialty_adhesive, stone_adhesive, grout, waterproofing, surface_prep, stone_care,
cleaning, screed, sound_control, cement_additive, 3d_mortar), description, 
technical_specs (open_time, pot_life, coverage_rate, compressive_strength, 
shear_bond_strength, application_thickness, cure_time, mixing_ratio, temperature_range),
grade_classification, substrate_compatibility (list), tile_compatibility (list),
recommended_use_cases (list), packaging (sizes list, shelf_life).
Use null for unknown fields. Include units for all values.
Return ONLY valid JSON."""

@tool
def extract_product_specs(content: str, source_url: str, content_type: str) -> dict:
    """Extract structured product data from raw crawled content using Gemini.
    
    This tool sends content to Gemini 2.5 Flash which extracts product specs,
    compatibility info, and technical data into a structured format.
    
    Args:
        content: Raw text content from crawler
        source_url: Source URL for provenance
        content_type: html, pdf, or docx
    
    Returns:
        Structured product record dict
    """
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    # For PDFs, also extract tables first
    if content_type == "pdf":
        from parser.pdf_table_parser import extract_tables_text
        table_text = extract_tables_text(content)
        content = f"TABLES:\n{table_text}\n\nFULL TEXT:\n{content}"
    
    response = llm.invoke(EXTRACTION_PROMPT.format(content=content[:8000]))
    data = json.loads(response.content)
    data["source_urls"] = [source_url]
    data["extracted_at"] = datetime.utcnow().isoformat()
    
    # Validate + confidence score
    from parser.field_validator import compute_confidence
    data["extraction_confidence"] = compute_confidence(data)
    data["needs_human_review"] = data["extraction_confidence"] < 0.6
    
    return data

@tool
def validate_product_schema(product: dict) -> dict:
    """Validate a product record against the Pydantic schema.
    
    Args:
        product: Product dict to validate
    
    Returns:
        {valid: bool, errors: list, confidence: float}
    """
    try:
        record = ProductRecord(**product)
        return {"valid": True, "errors": [], "confidence": record.extraction_confidence}
    except Exception as e:
        return {"valid": False, "errors": [str(e)], "confidence": 0.0}
```

## Confidence Scoring (`parser/field_validator.py`)

```python
def compute_confidence(product: dict) -> float:
    score = 0
    total = 12
    checks = [
        product.get("product_name"),
        product.get("sku"),
        product.get("product_family"),
        product.get("description"),
        product.get("technical_specs", {}).get("coverage_rate"),
        product.get("technical_specs", {}).get("open_time"),
        product.get("grade_classification"),
        len(product.get("substrate_compatibility", [])) > 0,
        len(product.get("tile_compatibility", [])) > 0,
        len(product.get("recommended_use_cases", [])) > 0,
        len(product.get("packaging", {}).get("sizes", [])) > 0,
        product.get("packaging", {}).get("shelf_life"),
    ]
    return sum(1 for c in checks if c) / total
```

## Version Tracking (`parser/version_tracker.py`)
- SQLite table: `product_versions(sku, version, data_json, extracted_at, diff_summary)`
- On each extraction: compare with previous, increment version if changed

## QA Report (`parser/qa_report.py`)
- Generates markdown with: total products, confidence distribution, flagged items, field fill rates

## Deliverable Checklist
- [ ] parse_node works as LangGraph node
- [ ] extract_product_specs tool uses Gemini 2.5 Flash via langchain-google-genai
- [ ] Pydantic schema validates all fields
- [ ] Confidence scoring flags low-quality extractions
- [ ] Version history tracked per SKU
- [ ] 30+ products with all fields populated
- [ ] QA report generated
