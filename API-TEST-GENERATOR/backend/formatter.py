"""
Test Formatter.
Cleans up, validates, and saves generated Pytest test files to disk.
Ensures all files have proper headers, imports, and formatting.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TestFormatter:
    """
    Formats and persists generated test code to the generated_tests directory.
    Adds file headers, validates imports, and organizes output files.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_all(self, test_results: list[dict], spec_id: str) -> list[str]:
        """
        Save all generated test files.
        Returns list of absolute file paths that were saved.
        """
        saved_paths = []

        for result in test_results:
            filename = result["filename"]
            code = result.get("code", "")
            endpoint = result.get("endpoint")

            if not code.strip():
                logger.warning(f"Skipping empty file: {filename}")
                continue

            # For per-endpoint files, prefix with spec_id to avoid collisions
            if filename == "conftest.py":
                output_filename = filename
            else:
                output_filename = f"{spec_id}_{filename}"

            formatted_code = self._format(code, filename, endpoint, spec_id)
            output_path = self.output_dir / output_filename

            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(formatted_code)
                saved_paths.append(str(output_path))
                logger.info(f"Saved: {output_path}")
            except Exception as e:
                logger.error(f"Failed to save {output_filename}: {e}")

        return saved_paths

    def _format(self, code: str, filename: str, endpoint: dict | None, spec_id: str) -> str:
        """
        Apply formatting steps to generated code:
        1. Add file header banner
        2. Ensure required imports are present
        3. Normalize line endings
        4. Ensure trailing newline
        """
        code = self._normalize_line_endings(code)
        code = self._ensure_imports(code)
        code = self._add_header(code, filename, endpoint, spec_id)
        code = self._ensure_trailing_newline(code)
        return code

    def _add_header(self, code: str, filename: str, endpoint: dict | None, spec_id: str) -> str:
        """
        Prepend a structured file header if one isn't already present.
        Avoids duplicating headers on conftest.py which Gemini already heads.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if endpoint:
            method = endpoint.get("method", "")
            path = endpoint.get("path", "")
            summary = endpoint.get("summary") or "No summary"
            header = (
                f"# ════════════════════════════════════════════════════\n"
                f"# Auto-generated API Tests\n"
                f"# Spec     : {spec_id}\n"
                f"# Endpoint : {method} {path}\n"
                f"# Summary  : {summary}\n"
                f"# Generated: {timestamp}\n"
                f"# Tool     : AI-Powered API Test Generator\n"
                f"# ════════════════════════════════════════════════════\n\n"
            )
        else:
            header = (
                f"# ════════════════════════════════════════════════════\n"
                f"# Auto-generated Pytest Configuration\n"
                f"# Spec     : {spec_id}\n"
                f"# Generated: {timestamp}\n"
                f"# Tool     : AI-Powered API Test Generator\n"
                f"# ════════════════════════════════════════════════════\n\n"
            )

        # Don't double-header if Gemini already put a comment at the top
        first_line = code.lstrip().split("\n")[0] if code.strip() else ""
        if first_line.startswith("#"):
            # Replace Gemini's first comment line with our header + their line
            return header + code
        else:
            return header + code

    def _ensure_imports(self, code: str) -> str:
        """
        Make sure `import requests` and `import pytest` appear in the file.
        Insert them at the top (after any module docstring) if missing.
        """
        has_requests = bool(re.search(r"^import requests", code, re.MULTILINE))
        has_pytest = bool(re.search(r"^import pytest", code, re.MULTILINE))

        if has_requests and has_pytest:
            return code

        missing_imports = []
        if not has_pytest:
            missing_imports.append("import pytest")
        if not has_requests:
            missing_imports.append("import requests")

        import_block = "\n".join(missing_imports) + "\n"

        # Insert after any leading comments or docstring
        lines = code.split("\n")
        insert_at = 0
        in_docstring = False
        docstring_char = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip leading comments
            if stripped.startswith("#"):
                insert_at = i + 1
                continue
            # Handle docstrings
            if not in_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                docstring_char = stripped[:3]
                if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                    # Single-line docstring
                    insert_at = i + 1
                    break
                in_docstring = True
                insert_at = i + 1
                continue
            if in_docstring:
                insert_at = i + 1
                if docstring_char in line:
                    break
                continue
            break

        lines.insert(insert_at, import_block)
        return "\n".join(lines)

    def _normalize_line_endings(self, code: str) -> str:
        """Normalize to Unix line endings."""
        return code.replace("\r\n", "\n").replace("\r", "\n")

    def _ensure_trailing_newline(self, code: str) -> str:
        """Ensure file ends with exactly one newline."""
        return code.rstrip("\n") + "\n"
