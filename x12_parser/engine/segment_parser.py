"""
X12 Segment Parser and Semantic Element Mapper.

Parses raw segments into structured JSON objects with human-readable keys,
component sub-element handling, and standard value formatting.
"""

from typing import Dict, List, Any, Optional, Union
from .tokenizer import RawSegment, X12Delimiters
from .dictionary import (
    get_segment_name,
    get_element_name,
    get_code_description,
    SEGMENT_ELEMENT_MAP,
)


class ParsedSegment:
    """Represents a fully parsed X12 segment with semantic field names."""

    def __init__(
        self,
        raw_segment: RawSegment,
        delimiters: X12Delimiters,
    ):
        self.segment_id = raw_segment.segment_id
        self.segment_name = get_segment_name(self.segment_id)
        self.line_number = raw_segment.line_number
        self.raw_elements = raw_segment.elements
        self.delimiters = delimiters
        self.fields: Dict[str, Any] = {}
        self._parse_fields()

    def _parse_fields(self) -> None:
        """Map raw elements to semantic field names and parse components."""
        comp_sep = self.delimiters.component_separator

        for idx, elem_val in enumerate(self.raw_elements, start=1):
            field_name = get_element_name(self.segment_id, idx)
            parsed_val = self._parse_element_value(self.segment_id, idx, elem_val, comp_sep)
            self.fields[field_name] = parsed_val

    def _parse_element_value(
        self,
        segment_id: str,
        pos: int,
        val: str,
        comp_sep: str,
    ) -> Any:
        """Parse element value, handling composites and whitespace."""
        val = val.strip()
        if not val:
            return ""

        # Special handling for BDS03 / BIN binary payloads: do not split by component separator
        if (segment_id == "BDS" and pos == 3) or (segment_id == "BIN" and pos == 2):
            return val

        # Check for component composite (e.g., HC:99214:25)
        if comp_sep in val:
            components = val.split(comp_sep)
            return self._parse_composite(segment_id, pos, components)

        return val

    def _parse_composite(
        self,
        segment_id: str,
        pos: int,
        components: List[str],
    ) -> Dict[str, Any]:
        """Convert composite data element parts into structured dict."""
        field_name = get_element_name(segment_id, pos)
        
        # Medical Procedure Identifier (e.g. HC:99213:25)
        if "procedure" in field_name or segment_id in ("SVC", "SV1", "SV2", "SV3"):
            res: Dict[str, Any] = {
                "qualifier": components[0] if len(components) > 0 else "",
                "code": components[1] if len(components) > 1 else "",
            }
            modifiers = [m for m in components[2:] if m]
            if modifiers:
                res["modifiers"] = modifiers
            res["raw"] = self.delimiters.component_separator.join(components)
            return res

        # Diagnosis Code Information (HI segment)
        if segment_id == "HI":
            res = {
                "qualifier": components[0] if len(components) > 0 else "",
                "code": components[1] if len(components) > 1 else "",
            }
            if len(components) > 2 and components[2]:
                res["present_on_admission"] = components[2]
            res["raw"] = self.delimiters.component_separator.join(components)
            return res

        # Claim status composite in STC segment
        if segment_id == "STC" and ("status" in field_name or pos in (1, 10, 11)):
            res = {
                "category_code": components[0] if len(components) > 0 else "",
                "status_code": components[1] if len(components) > 1 else "",
                "entity_identifier_code": components[2] if len(components) > 2 else "",
            }
            if len(components) > 3:
                res["code_list_qualifier_code"] = components[3]
            # Add descriptions
            res["category_description"] = get_code_description("claim_status_category_code", res["category_code"]) or ""
            res["raw"] = self.delimiters.component_separator.join(components)
            return res

        # Generic composite
        res = {"raw": self.delimiters.component_separator.join(components)}
        for i, comp in enumerate(components, start=1):
            res[f"component_{i}"] = comp
        return res

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_name": self.segment_name,
            "line_number": self.line_number,
            "fields": self.fields,
        }
