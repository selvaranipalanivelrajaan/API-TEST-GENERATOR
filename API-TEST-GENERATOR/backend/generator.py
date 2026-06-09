"""
Test Generator using Google Gemini 1.5 Flash.
Converts structured endpoint metadata into Pytest test code via AI.
Includes retry logic, prompt engineering, and structured output handling.
"""

import logging
import os
import re
import time
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

from backend.parser import EndpointInfo
from backend.prompt_builder import build_test_prompt, build_conftest_prompt

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-1.5-flash"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


class TestGenerator:
    """
    Orchestrates AI-powered test generation for all parsed endpoints.
    Uses Gemini 1.5 Flash via the google-generativeai SDK.
    """

    def __init__(self, base_url: Optional[str] = None):
        if not GEMINI_API_KEY:
            raise EnvironmentError(
                "GEMINI_API_KEY not found. "
                "Please set it in your .env file or environment variables."
            )

        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,       # Lower temperature = more consistent code
                top_p=0.95,
                max_output_tokens=8192,
            )
        )
        self.base_url = base_url or os.getenv("API_BASE_URL", "http://localhost:8000")
        logger.info(f"TestGenerator initialized with model: {GEMINI_MODEL}")

    def generate_all(self, endpoints: list[EndpointInfo], spec_id: str) -> list[dict]:
        """
        Generate tests for all endpoints plus a shared conftest.py.
        Returns a list of dicts: {filename, code, test_count, endpoint}
        """
        results = []

        # Generate conftest.py
        logger.info("Generating conftest.py...")
        conftest_code = self._generate_conftest(spec_id)
        results.append({
            "filename": f"conftest.py",
            "code": conftest_code,
            "test_count": 0,
            "endpoint": None
        })

        # Generate per-endpoint test files
        for i, endpoint in enumerate(endpoints, 1):
            op_id = endpoint.operation_id or (
                f"{endpoint.method.lower()}_{endpoint.path.strip('/').replace('/', '_')}"
            )
            logger.info(f"[{i}/{len(endpoints)}] Generating tests for: "
                        f"{endpoint.method} {endpoint.path}")

            code = self._generate_with_retry(endpoint)
            test_count = self._count_tests(code)

            safe_op_id = re.sub(r"[^a-zA-Z0-9_]", "_", op_id)
            filename = f"test_{safe_op_id}.py"

            results.append({
                "filename": filename,
                "code": code,
                "test_count": test_count,
                "endpoint": endpoint.dict()
            })

            logger.info(f"  → {test_count} tests generated → {filename}")

            # Brief pause between API calls to avoid rate limiting
            if i < len(endpoints):
                time.sleep(0.5)

        return results

    def _generate_with_retry(self, endpoint: EndpointInfo) -> str:
        """
        Call Gemini API with exponential backoff retry.
        Returns generated Python test code as a string.
        """
        prompt = build_test_prompt(endpoint, self.base_url)
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug(f"Gemini API call attempt {attempt} for "
                             f"{endpoint.method} {endpoint.path}")
                response = self.model.generate_content(prompt)

                # Extract text from response
                code = self._extract_code(response)
                if code:
                    return code
                else:
                    raise ValueError("Gemini returned empty response.")

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)

        # All retries exhausted — return a fallback stub
        logger.error(f"All {MAX_RETRIES} attempts failed for "
                     f"{endpoint.method} {endpoint.path}. Error: {last_error}")
        return self._fallback_stub(endpoint)

    def _generate_conftest(self, spec_id: str) -> str:
        """Generate the conftest.py file."""
        prompt = build_conftest_prompt(spec_id, self.base_url)
        try:
            response = self.model.generate_content(prompt)
            return self._extract_code(response)
        except Exception as e:
            logger.warning(f"conftest.py generation failed: {e}. Using default.")
            return self._default_conftest(spec_id)

    def _extract_code(self, response) -> str:
        """
        Extract clean Python code from a Gemini response.
        Strips markdown code fences if present.
        """
        if not response or not response.text:
            return ""

        text = response.text.strip()

        # Strip markdown code fences
        text = re.sub(r"^```python\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text.strip())

        return text.strip()

    def _count_tests(self, code: str) -> int:
        """Count the number of test functions in generated code."""
        return len(re.findall(r"^\s*def test_", code, re.MULTILINE))

    def _fallback_stub(self, endpoint: EndpointInfo) -> str:
        """
        Return a minimal stub test file when Gemini generation fails.
        Ensures the test suite is always complete even on API errors.
        """
        method = endpoint.method.upper()
        path = endpoint.path
        op_id = endpoint.operation_id or f"{method.lower()}_{path.strip('/').replace('/', '_')}"
        safe_class = re.sub(r"[^a-zA-Z0-9]", "", op_id.title())

        return f'''# Generated test file for {method} {path}
# NOTE: This is a fallback stub — AI generation was unavailable.
# Fill in the test logic manually.

import pytest
import requests

BASE_URL = "{self.base_url}"
ENDPOINT = "{path}"


class Test{safe_class}:
    """Tests for {method} {path}"""

    def test_positive_valid_request(self):
        """Test: Valid request returns expected success status."""
        # Arrange
        url = BASE_URL + ENDPOINT
        # Act
        response = requests.{method.lower()}(url)
        # Assert
        assert response.status_code in [200, 201, 204], (
            f"Expected 2xx but got {{response.status_code}}: {{response.text}}"
        )

    def test_negative_invalid_request(self):
        """Test: Invalid request returns error status."""
        # Arrange
        url = BASE_URL + ENDPOINT
        # Act - send intentionally bad data
        response = requests.{method.lower()}(url, json={{"__invalid__": True}})
        # Assert
        assert response.status_code in [400, 422, 405], (
            f"Expected 4xx but got {{response.status_code}}"
        )
'''

    def _default_conftest(self, spec_id: str) -> str:
        """Return a default conftest.py when Gemini cannot generate one."""
        return f'''# conftest.py - Shared fixtures for {spec_id} API test suite

import pytest
import requests


BASE_URL = "{self.base_url}"


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring a live API server"
    )


@pytest.fixture(scope="session")
def session():
    """Shared requests Session with default headers."""
    s = requests.Session()
    s.headers.update({{
        "Content-Type": "application/json",
        "Accept": "application/json"
    }})
    yield s
    s.close()


@pytest.fixture
def api_headers():
    """Standard API request headers."""
    return {{
        "Content-Type": "application/json",
        "Accept": "application/json"
    }}


@pytest.fixture
def base_url():
    """Base URL for all API requests."""
    return BASE_URL
'''
