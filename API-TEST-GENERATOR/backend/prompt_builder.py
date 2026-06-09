"""
Prompt Builder for Gemini API Test Generation.
Constructs detailed, structured prompts from parsed OpenAPI endpoint metadata
to guide Gemini 1.5 Flash in generating comprehensive Pytest test cases.
"""

import json
import logging
from typing import Optional

from backend.parser import EndpointInfo

logger = logging.getLogger(__name__)


def _format_parameters(endpoint: EndpointInfo) -> str:
    """Format parameters section of the prompt."""
    if not endpoint.parameters:
        return "  None"

    lines = []
    for p in endpoint.parameters:
        req = "REQUIRED" if p.required else "optional"
        ex = f", example={p.example!r}" if p.example is not None else ""
        lines.append(
            f"  - {p.name} (in={p.location}, type={p.schema_type}, {req}{ex})"
        )
    return "\n".join(lines)


def _format_request_body(endpoint: EndpointInfo) -> str:
    """Format request body section of the prompt."""
    if not endpoint.request_body:
        return "  None"

    rb = endpoint.request_body
    lines = [f"  content-type: {rb.content_type}",
             f"  required: {rb.required}"]

    if rb.schema_properties:
        lines.append("  fields:")
        for name, info in rb.schema_properties.items():
            req_flag = "(required)" if name in rb.required_fields else "(optional)"
            type_info = info.get("type", "string")
            extra = []
            if info.get("format"):
                extra.append(f"format={info['format']}")
            if info.get("minimum") is not None:
                extra.append(f"min={info['minimum']}")
            if info.get("maximum") is not None:
                extra.append(f"max={info['maximum']}")
            if info.get("minLength") is not None:
                extra.append(f"minLen={info['minLength']}")
            if info.get("maxLength") is not None:
                extra.append(f"maxLen={info['maxLength']}")
            if info.get("enum"):
                extra.append(f"enum={info['enum']}")
            if info.get("example") is not None:
                extra.append(f"example={info['example']!r}")
            extra_str = f" [{', '.join(extra)}]" if extra else ""
            lines.append(f"    - {name}: {type_info} {req_flag}{extra_str}")
    else:
        lines.append("  fields: (schema not specified)")

    if rb.example:
        lines.append(f"  example body: {json.dumps(rb.example)}")

    return "\n".join(lines)


def _format_responses(endpoint: EndpointInfo) -> str:
    """Format responses section of the prompt."""
    if not endpoint.responses:
        return "  None"

    lines = []
    for r in endpoint.responses:
        desc = f" - {r.description}" if r.description else ""
        lines.append(f"  - {r.status_code}{desc}")
        if r.schema_properties:
            fields = ", ".join(f"{k}: {v}" for k, v in r.schema_properties.items())
            lines.append(f"    response fields: {fields}")

    return "\n".join(lines)


def build_test_prompt(endpoint: EndpointInfo, base_url: str = "http://localhost:8000") -> str:
    """
    Build a comprehensive Gemini prompt for a single endpoint.
    The prompt instructs Gemini to produce ready-to-run Pytest code.
    """
    method = endpoint.method.upper()
    path = endpoint.path
    op_id = endpoint.operation_id or f"{method.lower()}_{path.strip('/').replace('/', '_')}"
    summary = endpoint.summary or "No summary provided"

    # Build path params list for substitution hints
    path_params = [p for p in endpoint.parameters if p.location == "path"]
    query_params = [p for p in endpoint.parameters if p.location == "query"]

    path_params_str = _format_parameters(EndpointInfo(
        path=path, method=method, parameters=path_params))
    query_params_str = _format_parameters(EndpointInfo(
        path=path, method=method, parameters=query_params))
    request_body_str = _format_request_body(endpoint)
    responses_str = _format_responses(endpoint)

    success_codes = [r.status_code for r in endpoint.responses
                     if r.status_code.startswith("2")]
    success_code = success_codes[0] if success_codes else "200"

    prompt = f"""
You are a senior software engineer specializing in API test automation.
Generate a complete, production-ready Pytest test file for the following API endpoint.

═══════════════════════════════════════════════
ENDPOINT DETAILS
═══════════════════════════════════════════════
Operation ID : {op_id}
Summary      : {summary}
Method       : {method}
Path         : {path}
Base URL     : {base_url}
Full URL     : {base_url}{path}
Tags         : {', '.join(endpoint.tags) or 'None'}

PATH PARAMETERS:
{path_params_str}

QUERY PARAMETERS:
{query_params_str}

REQUEST BODY:
{request_body_str}

RESPONSES:
{responses_str}

═══════════════════════════════════════════════
TEST REQUIREMENTS
═══════════════════════════════════════════════

Generate exactly these test categories:

1. POSITIVE TESTS (happy path):
   - Valid request with all required fields → expect {success_code}
   - Valid request with optional fields included → expect {success_code}
   - Minimal valid request (only required fields) → expect {success_code}

2. NEGATIVE TESTS (validation failures):
   - Missing required fields → expect 400 or 422
   - Extra/unknown fields in body (should be ignored or rejected)
   - Wrong HTTP method → expect 405
   - Invalid content-type header (if body expected) → expect 400 or 415

3. BOUNDARY TESTS:
   - String fields: empty string, single char, very long string (1000+ chars)
   - Numeric fields: 0, -1, very large number, float when int expected
   - Required field as null → expect 400 or 422

4. INVALID DATA TYPE TESTS:
   - String field with integer value
   - Integer field with string value
   - Boolean field with string "true"/"false"

5. STATUS CODE VALIDATION:
   - Assert exact status codes for each scenario
   - Assert response is JSON where expected
   - Assert required fields exist in response body

═══════════════════════════════════════════════
CODE REQUIREMENTS
═══════════════════════════════════════════════

- Use Python `requests` library for HTTP calls
- Use `pytest` and standard `assert` statements
- Define BASE_URL = "{base_url}" at the top of the file
- Define ENDPOINT = "{path}" below BASE_URL
- For path parameters: use realistic example values (e.g., user_id=1, item_id=42)
- Group tests into a class: `class Test{op_id.replace("_", " ").title().replace(" ", "")}:`
- Each test method must have a clear docstring explaining what it tests
- Add `# Arrange / # Act / # Assert` comments to structure each test
- Import: `import requests`, `import pytest`
- Do NOT use any mocking or test fixtures for HTTP calls — use real requests
- Do NOT use any external test data files — all test data inline
- Handle cases where path has parameters like {{user_id}} by substituting with f-strings
- The file must be runnable as-is with: pytest <filename>.py

Start your response DIRECTLY with the Python code.
Do not include any explanation, markdown fences, or preamble.
The very first line must be: # Generated test file for {method} {path}
""".strip()

    return prompt


def build_conftest_prompt(spec_id: str, base_url: str = "http://localhost:8000") -> str:
    """Build a prompt to generate a shared conftest.py for the test suite."""
    return f"""
You are a senior Python test engineer.
Generate a `conftest.py` file for a Pytest test suite that tests a REST API.

Requirements:
- BASE_URL = "{base_url}"
- SPEC_ID = "{spec_id}"
- Define a shared `session` fixture (scope="session") that returns a configured requests.Session
- Add a custom marker `@pytest.mark.integration` for live API tests
- Add a fixture `api_headers` returning {{"Content-Type": "application/json", "Accept": "application/json"}}
- Add a `pytest_configure` hook registering the integration marker
- Add comments throughout

Start directly with Python code, no markdown fences, no preamble.
First line: # conftest.py - Shared fixtures for {spec_id} API test suite
""".strip()
