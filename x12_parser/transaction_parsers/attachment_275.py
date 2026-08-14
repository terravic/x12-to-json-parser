"""
X12 275 (Patient Information Attachment Envelope) Parser.

Extracts embedded C-CDA XML payloads from BDS/BIN segments and invokes
the clinical CCDAParser to produce structured `attached_clinical_data`.
"""

import base64
import logging
from typing import Dict, List, Any, Optional
from ..engine.segment_parser import ParsedSegment
from ..engine.dictionary import get_code_description
from ..clinical_parsers.ccda_parser import CCDAParser

logger = logging.getLogger(__name__)


class Attachment275Parser:
    """Parses X12 275 Attachment Envelopes and seamlessly parses embedded C-CDA XML payloads."""

    @classmethod
    def parse_275(cls, segments: List[ParsedSegment]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "transaction_type": "275",
            "transaction_description": "Patient Information Attachment Envelope",
            "beginning_segment": {},
            "submitter": {},
            "receiver": {},
            "patient": {},
            "attachment_metadata": {},
            "raw_payload_info": {},
            "attached_clinical_data": {},  # Structured clinical JSON parsed from C-CDA XML
        }

        current_entity_loop = ""
        raw_payload = ""
        filter_type = ""
        payload_length = 0

        for seg in segments:
            seg_id = seg.segment_id
            f = seg.fields

            if seg_id == "BGN":
                result["beginning_segment"] = {
                    "purpose_code": f.get("transaction_set_purpose_code", ""),
                    "reference_identification": f.get("reference_identification", ""),
                    "date": f.get("date", ""),
                    "time": f.get("time", ""),
                    "action_code": f.get("action_code", ""),
                }

            elif seg_id == "NM1":
                entity_code = f.get("entity_identifier_code", "")
                entity_info = {
                    "entity_identifier_code": entity_code,
                    "entity_type": "Person" if f.get("entity_type_qualifier") == "1" else "Non-Person/Organization",
                    "name_last_or_organization": f.get("name_last_or_organization_name", ""),
                    "name_first": f.get("name_first", ""),
                    "name_middle": f.get("name_middle", ""),
                    "identification_code_qualifier": f.get("identification_code_qualifier", ""),
                    "identification_code": f.get("identification_code", ""),
                }

                if entity_code == "41":  # Submitter
                    result["submitter"] = entity_info
                    current_entity_loop = "submitter"
                elif entity_code == "40":  # Receiver
                    result["receiver"] = entity_info
                    current_entity_loop = "receiver"
                elif entity_code in ("QC", "IL", "03"):  # Patient / Member
                    result["patient"] = entity_info
                    current_entity_loop = "patient"

            elif seg_id == "N3":
                addr = {"address_line_1": f.get("address_line_1", ""), "address_line_2": f.get("address_line_2", "")}
                if current_entity_loop == "patient":
                    result["patient"]["address"] = addr

            elif seg_id == "N4":
                geo = {"city": f.get("city_name", ""), "state": f.get("state_or_province_code", ""), "postal_code": f.get("postal_code", "")}
                if current_entity_loop == "patient":
                    result["patient"]["geographic_location"] = geo

            elif seg_id == "DMG":
                if current_entity_loop == "patient":
                    result["patient"]["demographics"] = {
                        "date_of_birth": f.get("date_of_birth", ""),
                        "gender": f.get("gender_code", ""),
                    }

            elif seg_id == "CAT":
                struct_code = f.get("attachment_structure_code", "")
                type_code = f.get("attachment_type_code", "")
                ctrl_num = f.get("attachment_control_number", "")
                result["attachment_metadata"] = {
                    "attachment_structure_code": struct_code,
                    "attachment_type_code": type_code,
                    "attachment_type_description": get_code_description("attachment_report_type_code", type_code) or "",
                    "attachment_control_number": ctrl_num,
                }

            elif seg_id == "PID":
                result["attachment_metadata"]["description"] = f.get("description", "") or f.get("product_description_code", "")

            elif seg_id == "BDS":
                # BDS01: Filter ID / Encoding (e.g. 'XML', 'B64', 'NONE')
                # BDS02: Binary Length
                # BDS03: Binary Data Payload
                filter_type = f.get("filter_id_code", "XML")
                len_str = f.get("binary_data_length", "0")
                payload_length = int(len_str) if len_str and str(len_str).isdigit() else 0
                raw_payload = f.get("binary_data", "")

            elif seg_id == "BIN":
                # BIN01: Length
                # BIN02: Data
                len_str = f.get("binary_data_length", "0")
                payload_length = int(len_str) if len_str and str(len_str).isdigit() else 0
                raw_payload = f.get("binary_data", "")
                filter_type = "BIN"

        # Record payload metadata
        result["raw_payload_info"] = {
            "format": filter_type or "XML",
            "length_bytes": payload_length or len(raw_payload),
            "is_base64": not raw_payload.strip().startswith("<") if raw_payload else False,
        }

        # Parse C-CDA XML if payload present
        if raw_payload:
            try:
                ccda_parser = CCDAParser(raw_payload)
                clinical_data = ccda_parser.parse()
                result["attached_clinical_data"] = clinical_data
            except Exception as e:
                logger.warning(f"Error parsing attached C-CDA XML: {e}")
                result["attached_clinical_data"] = {
                    "error": f"Failed to parse clinical payload: {str(e)}",
                    "raw_preview": raw_payload[:200] + "..." if len(raw_payload) > 200 else raw_payload
                }

        return result
