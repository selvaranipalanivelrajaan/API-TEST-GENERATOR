"""
OpenAPI Specification Parser.
Supports OpenAPI 3.x in YAML and JSON formats.
Extracts paths, methods, parameters, request bodies, response schemas, and status codes.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Pydantic models for structured endpoint data
# ─────────────────────────────────────────────

class ParameterInfo(BaseModel):
    name: str
    location: str  # query, path, header, cookie
    required: bool = False
    schema_type: str = "string"
    description: Optional[str] = None
    example: Optional[Any] = None


class RequestBodyInfo(BaseModel):
    required: bool = False
    content_type: str = "application/json"
    schema_properties: dict = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    example: Optional[dict] = None


class ResponseInfo(BaseModel):
    status_code: str
    description: str = ""
    schema_type: Optional[str] = None
    schema_properties: dict = Field(default_factory=dict)


class EndpointInfo(BaseModel):
    path: str
    method: str
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    parameters: list[ParameterInfo] = Field(default_factory=list)
    request_body: Optional[RequestBodyInfo] = None
    responses: list[ResponseInfo] = Field(default_factory=list)
    security: list[dict] = Field(default_factory=list)


# ─────────────────────────────────────────────
# Parser class
# ─────────────────────────────────────────────

class OpenAPIParser:
    """
    Parses an OpenAPI 3.x specification from YAML or JSON.
    Returns a list of EndpointInfo objects for downstream test generation.
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.spec: dict = {}
        self.components: dict = {}

    def load(self) -> dict:
        """Load and parse the YAML or JSON file."""
        suffix = self.file_path.suffix.lower()
        with open(self.file_path, "r", encoding="utf-8") as f:
            if suffix in {".yaml", ".yml"}:
                self.spec = yaml.safe_load(f)
            elif suffix == ".json":
                self.spec = json.load(f)
            else:
                raise ValueError(f"Unsupported file extension: {suffix}")

        if not isinstance(self.spec, dict):
            raise ValueError("OpenAPI spec must be a YAML/JSON object (dict).")

        # Store components for $ref resolution
        self.components = self.spec.get("components", {})
        logger.info(f"Loaded spec: {self.spec.get('info', {}).get('title', 'Unknown')} "
                    f"v{self.spec.get('info', {}).get('version', '?')}")
        return self.spec

    def parse(self) -> list[EndpointInfo]:
        """Parse all endpoints from the loaded spec."""
        self.load()
        endpoints: list[EndpointInfo] = []
        paths = self.spec.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Path-level parameters (inherited by all operations)
            path_level_params = path_item.get("parameters", [])

            http_methods = ["get", "post", "put", "patch", "delete", "head", "options"]
            for method in http_methods:
                operation = path_item.get(method)
                if not operation:
                    continue

                endpoint = self._parse_operation(path, method, operation, path_level_params)
                endpoints.append(endpoint)
                logger.debug(f"Parsed: {method.upper()} {path}")

        logger.info(f"Total endpoints parsed: {len(endpoints)}")
        return endpoints

    def _parse_operation(
        self,
        path: str,
        method: str,
        operation: dict,
        path_level_params: list
    ) -> EndpointInfo:
        """Parse a single HTTP operation into an EndpointInfo."""
        # Merge path-level params with operation-level params
        operation_params = operation.get("parameters", [])
        all_params_raw = {p.get("name"): p for p in path_level_params}
        all_params_raw.update({p.get("name"): p for p in operation_params})

        parameters = [
            self._parse_parameter(p) for p in all_params_raw.values()
            if isinstance(p, dict)
        ]

        # Request body
        request_body = None
        if "requestBody" in operation:
            request_body = self._parse_request_body(operation["requestBody"])

        # Responses
        responses = self._parse_responses(operation.get("responses", {}))

        return EndpointInfo(
            path=path,
            method=method.upper(),
            operation_id=operation.get("operationId"),
            summary=operation.get("summary"),
            description=operation.get("description"),
            tags=operation.get("tags", []),
            parameters=parameters,
            request_body=request_body,
            responses=responses,
            security=operation.get("security", [])
        )

    def _parse_parameter(self, param: dict) -> ParameterInfo:
        """Parse a single parameter definition."""
        schema = self._resolve_ref(param.get("schema", {}))
        return ParameterInfo(
            name=param.get("name", "unknown"),
            location=param.get("in", "query"),
            required=param.get("required", False),
            schema_type=schema.get("type", "string"),
            description=param.get("description"),
            example=param.get("example") or schema.get("example")
        )

    def _parse_request_body(self, request_body: dict) -> RequestBodyInfo:
        """Parse a requestBody object."""
        request_body = self._resolve_ref(request_body)
        content = request_body.get("content", {})

        # Prefer application/json, fall back to first available
        content_type = "application/json"
        media_type_obj = content.get("application/json", {})
        if not media_type_obj and content:
            content_type = next(iter(content))
            media_type_obj = content[content_type]

        schema = self._resolve_ref(media_type_obj.get("schema", {}))
        properties = {}
        required_fields = []

        if schema.get("type") == "object" or "properties" in schema:
            raw_props = schema.get("properties", {})
            for prop_name, prop_schema in raw_props.items():
                resolved = self._resolve_ref(prop_schema)
                properties[prop_name] = {
                    "type": resolved.get("type", "string"),
                    "example": resolved.get("example"),
                    "description": resolved.get("description"),
                    "format": resolved.get("format"),
                    "minimum": resolved.get("minimum"),
                    "maximum": resolved.get("maximum"),
                    "minLength": resolved.get("minLength"),
                    "maxLength": resolved.get("maxLength"),
                    "enum": resolved.get("enum")
                }
            required_fields = schema.get("required", [])

        # Try to get an example
        example = media_type_obj.get("example") or schema.get("example")

        return RequestBodyInfo(
            required=request_body.get("required", False),
            content_type=content_type,
            schema_properties=properties,
            required_fields=required_fields,
            example=example if isinstance(example, dict) else None
        )

    def _parse_responses(self, responses: dict) -> list[ResponseInfo]:
        """Parse all response definitions."""
        result = []
        for status_code, response in responses.items():
            response = self._resolve_ref(response)
            description = response.get("description", "")

            # Try to extract schema from response content
            schema_type = None
            schema_properties = {}
            content = response.get("content", {})
            if content:
                media_obj = content.get("application/json", next(iter(content.values()), {}))
                schema = self._resolve_ref(media_obj.get("schema", {}))
                schema_type = schema.get("type")
                if "properties" in schema:
                    schema_properties = {
                        k: self._resolve_ref(v).get("type", "string")
                        for k, v in schema.get("properties", {}).items()
                    }

            result.append(ResponseInfo(
                status_code=str(status_code),
                description=description,
                schema_type=schema_type,
                schema_properties=schema_properties
            ))

        return result

    def _resolve_ref(self, obj: Any) -> dict:
        """
        Recursively resolve $ref pointers within the spec.
        Handles simple single-level $ref resolution from #/components/...
        """
        if not isinstance(obj, dict):
            return obj if isinstance(obj, dict) else {}

        if "$ref" in obj:
            ref_path = obj["$ref"]
            return self._lookup_ref(ref_path)

        return obj

    def _lookup_ref(self, ref_path: str) -> dict:
        """Navigate the spec to resolve a $ref string like '#/components/schemas/User'."""
        if not ref_path.startswith("#/"):
            logger.warning(f"External $ref not supported: {ref_path}")
            return {}

        parts = ref_path.lstrip("#/").split("/")
        node = self.spec
        for part in parts:
            if isinstance(node, dict):
                node = node.get(part, {})
            else:
                return {}

        # Recursively resolve if the resolved node also has a $ref
        if isinstance(node, dict) and "$ref" in node:
            return self._lookup_ref(node["$ref"])

        return node if isinstance(node, dict) else {}
