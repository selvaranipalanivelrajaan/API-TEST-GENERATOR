"""
FastAPI backend for AI-Powered API Test Generator.
Handles file upload, OpenAPI parsing, test generation, and downloads.
"""

import os
import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from backend.parser import OpenAPIParser
from backend.generator import TestGenerator
from backend.formatter import TestFormatter
from backend.zip_exporter import ZipExporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Directories
BASE_DIR = Path(__file__).parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
GENERATED_DIR = BASE_DIR / "generated_tests"

UPLOADS_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="AI-Powered API Test Generator",
    description="Automatically generate Pytest API test cases from OpenAPI/Swagger specifications.",
    version="1.0.0"
)

# Allow Streamlit frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────

class UploadResponse(BaseModel):
    message: str
    spec_id: str
    endpoints: list
    total_endpoints: int

class GenerateRequest(BaseModel):
    spec_id: str

class GenerateResponse(BaseModel):
    message: str
    test_files: list[str]
    total_tests_generated: int

# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


@app.post("/upload-spec", response_model=UploadResponse)
async def upload_spec(file: UploadFile = File(...)):
    """
    Upload an OpenAPI YAML or JSON specification file.
    Parses the spec and returns structured endpoint metadata.
    """
    logger.info(f"Received file upload: {file.filename}")

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".yaml", ".yml", ".json"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Upload a .yaml, .yml, or .json file."
        )

    # Save uploaded file
    spec_id = Path(file.filename).stem.replace(" ", "_")
    save_path = UPLOADS_DIR / f"{spec_id}{suffix}"

    try:
        contents = await file.read()
        with open(save_path, "wb") as f:
            f.write(contents)
        logger.info(f"File saved to {save_path}")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Parse the spec
    try:
        parser = OpenAPIParser(str(save_path))
        endpoints = parser.parse()
        logger.info(f"Parsed {len(endpoints)} endpoints from spec.")
    except Exception as e:
        logger.error(f"Failed to parse spec: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to parse OpenAPI spec: {str(e)}")

    # Serialize endpoints for JSON response
    endpoints_data = [ep.dict() for ep in endpoints]

    return UploadResponse(
        message="Specification parsed successfully.",
        spec_id=spec_id,
        endpoints=endpoints_data,
        total_endpoints=len(endpoints_data)
    )


@app.post("/generate-tests", response_model=GenerateResponse)
async def generate_tests(request: GenerateRequest):
    """
    Generate Pytest test cases for all endpoints in the uploaded spec.
    Uses Gemini 1.5 Flash to create positive, negative, and boundary tests.
    """
    spec_id = request.spec_id
    logger.info(f"Generating tests for spec_id: {spec_id}")

    # Find the uploaded spec file
    spec_file = None
    for ext in [".yaml", ".yml", ".json"]:
        candidate = UPLOADS_DIR / f"{spec_id}{ext}"
        if candidate.exists():
            spec_file = candidate
            break

    if not spec_file:
        raise HTTPException(
            status_code=404,
            detail=f"Spec file for ID '{spec_id}' not found. Please upload first."
        )

    # Parse endpoints
    try:
        parser = OpenAPIParser(str(spec_file))
        endpoints = parser.parse()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse spec: {str(e)}")

    # Generate tests via Gemini
    try:
        generator = TestGenerator()
        raw_tests = generator.generate_all(endpoints, spec_id)
    except Exception as e:
        logger.error(f"Test generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Test generation failed: {str(e)}")

    # Format and save test files
    try:
        formatter = TestFormatter(GENERATED_DIR)
        saved_files = formatter.save_all(raw_tests, spec_id)
    except Exception as e:
        logger.error(f"Failed to save test files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save test files: {str(e)}")

    total_tests = sum(t.get("test_count", 0) for t in raw_tests)
    logger.info(f"Generated {total_tests} tests across {len(saved_files)} files.")

    return GenerateResponse(
        message=f"Successfully generated {total_tests} tests in {len(saved_files)} file(s).",
        test_files=[str(Path(f).name) for f in saved_files],
        total_tests_generated=total_tests
    )


@app.get("/download/{filename}")
async def download_file(filename: str):
    """
    Download a single generated test file.
    """
    file_path = GENERATED_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    logger.info(f"Downloading file: {filename}")
    return FileResponse(
        path=str(file_path),
        media_type="text/x-python",
        filename=filename
    )


@app.get("/download-zip/{spec_id}")
async def download_zip(spec_id: str):
    """
    Download all generated test files for a spec as a ZIP archive.
    """
    logger.info(f"Creating ZIP for spec_id: {spec_id}")

    try:
        exporter = ZipExporter(GENERATED_DIR)
        zip_path = exporter.create_zip(spec_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"ZIP creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP: {str(e)}")

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=Path(zip_path).name
    )


@app.get("/list-tests/{spec_id}")
async def list_tests(spec_id: str):
    """
    List all generated test files for a given spec_id.
    """
    files = list(GENERATED_DIR.glob(f"{spec_id}_*.py"))
    if not files:
        return {"spec_id": spec_id, "files": [], "message": "No test files found."}

    return {
        "spec_id": spec_id,
        "files": [f.name for f in sorted(files)],
        "total": len(files)
    }


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
