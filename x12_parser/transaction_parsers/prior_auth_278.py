"""
X12 278 (Health Care Services Review - Prior Authorization Request & Response) Parser.
"""

from typing import Dict, List, Any, Optional
from ..engine.segment_parser import ParsedSegment
from ..engine.dictionary import get_code_description


class PriorAuthParser:
    """Parses X12 278 Prior Authorization transactions."""

    @classmethod
    def parse_278(cls, segments: List[ParsedSegment]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "transaction_type": "278",
            "transaction_description": "Health Care Services Review (Prior Authorization)",
            "utilization_management_organization": {},
            "requester": {},
            "subscriber": {},
            "events": [],
        }

        current_event: Optional[Dict[str, Any]] = None
        current_service: Optional[Dict[str, Any]] = None

        for seg in segments:
            seg_id = seg.segment_id
            f = seg.fields

            if seg_id == "BHT":
                result["beginning_of_hierarchical_transaction"] = {
                    "structure_code": f.get("hierarchical_structure_code", ""),
                    "purpose_code": f.get("beginning_transaction_purpose_code", ""),
                    "reference_identification": f.get("reference_identification", ""),
                    "date": f.get("date", ""),
                    "time": f.get("time", ""),
                }

            elif seg_id == "NM1":
                entity_code = f.get("entity_identifier_code", "")
                entity_info = {
                    "entity_identifier_code": entity_code,
                    "name_last_or_organization": f.get("name_last_or_organization_name", ""),
                    "name_first": f.get("name_first", ""),
                    "identification_code_qualifier": f.get("identification_code_qualifier", ""),
                    "identification_code": f.get("identification_code", ""),
                }
                if entity_code in ("PR", "UM", "40"):
                    result["utilization_management_organization"] = entity_info
                elif entity_code in ("1P", "FA", "85", "41"):
                    result["requester"] = entity_info
                elif entity_code == "IL":
                    result["subscriber"] = entity_info
                elif entity_code in ("82", "77", "1P") and current_event:
                    current_event["service_provider"] = entity_info

            elif seg_id == "UM":
                current_event = {
                    "request_category_code": f.get("request_category_code", ""),
                    "certification_type_code": f.get("certification_type_code", ""),
                    "service_type_code": f.get("service_type_code", ""),
                    "level_of_service": f.get("level_of_service_code", ""),
                    "review_results": [],
                    "services": [],
                    "diagnoses": [],
                }
                result["events"].append(current_event)
                current_service = None

            elif seg_id == "HCR":
                action_code = f.get("action_code", "")
                hcr_info = {
                    "action_code": action_code,
                    "action_description": get_code_description("action_code", action_code) or "",
                    "review_identification_number": f.get("review_identification_number", ""),
                    "approval_status": "Approved" if action_code in ("A1", "A2") else ("Denied" if action_code == "A3" else "Pended"),
                }
                if current_service is not None:
                    current_service["review_result"] = hcr_info
                elif current_event is not None:
                    current_event["review_results"].append(hcr_info)

            elif seg_id == "HI" and current_event is not None:
                for elem_k, elem_v in f.items():
                    if isinstance(elem_v, dict) and elem_v.get("code"):
                        current_event["diagnoses"].append(elem_v)

            elif seg_id in ("SV1", "SV2", "SV3") and current_event is not None:
                current_service = {
                    "service_type": "professional" if seg_id == "SV1" else ("institutional" if seg_id == "SV2" else "dental"),
                    "procedure": f.get("composite_medical_procedure_identifier", {}),
                    "charge_amount": f.get("line_item_charge_amount", ""),
                    "service_unit_count": f.get("service_unit_count", ""),
                }
                current_event["services"].append(current_service)

            elif seg_id == "PWK" and current_event is not None:
                pwk_type = f.get("attachment_report_type_code", "")
                current_event["paperwork_attachment"] = {
                    "attachment_report_type_code": pwk_type,
                    "report_type_description": get_code_description("attachment_report_type_code", pwk_type) or "",
                    "transmission_code": f.get("attachment_transmission_code", ""),
                    "control_number": f.get("attachment_control_number", ""),
                }

        return result
