"""
X12 277 (Health Care Information Status Notification / Request for Additional Information) Parser.

Specifically detects and extracts requested documentation items into a `required_attachments` array.
"""

from typing import Dict, List, Any, Optional
from ..engine.segment_parser import ParsedSegment
from ..engine.dictionary import get_code_description


class StatusRequest277Parser:
    """Parses X12 277 transactions and flags requested clinical attachments."""

    @classmethod
    def parse_277(cls, segments: List[ParsedSegment]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "transaction_type": "277",
            "transaction_description": "Health Care Information Status Notification / Request for Additional Information",
            "information_source": {},
            "information_receiver": {},
            "service_provider": {},
            "subscribers": [],
            "required_attachments": [],  # Flagged clinical documentation requests
            "claim_statuses": [],
        }

        current_subscriber: Optional[Dict[str, Any]] = None
        current_claim: Optional[Dict[str, Any]] = None
        current_entity_loop = ""

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
                    "entity_type": "Person" if f.get("entity_type_qualifier") == "1" else "Non-Person/Organization",
                    "name_last_or_organization": f.get("name_last_or_organization_name", ""),
                    "name_first": f.get("name_first", ""),
                    "name_middle": f.get("name_middle", ""),
                    "identification_code_qualifier": f.get("identification_code_qualifier", ""),
                    "identification_code": f.get("identification_code", ""),
                }

                if entity_code == "PR":  # Payer / Information Source
                    result["information_source"] = entity_info
                    current_entity_loop = "source"
                elif entity_code == "41":  # Submitter / Receiver
                    result["information_receiver"] = entity_info
                    current_entity_loop = "receiver"
                elif entity_code in ("1P", "FA", "85"):  # Billing Provider
                    result["service_provider"] = entity_info
                    current_entity_loop = "provider"
                elif entity_code in ("IL", "QC"):  # Subscriber / Patient
                    current_subscriber = {
                        "entity_code": entity_code,
                        "subscriber_name": entity_info,
                        "claims": [],
                    }
                    result["subscribers"].append(current_subscriber)
                    current_entity_loop = "subscriber"

            elif seg_id == "TRN":
                # Claim tracking trace
                trace_type = f.get("trace_type_code", "")
                trace_num = f.get("reference_identification_trace_number", "")
                if current_subscriber is not None:
                    current_claim = {
                        "claim_tracking_number": trace_num,
                        "trace_type": trace_type,
                        "status_information": [],
                        "paperwork_requests": [],
                        "references": {},
                    }
                    current_subscriber["claims"].append(current_claim)
                    result["claim_statuses"].append(current_claim)

            elif seg_id == "REF" and current_claim is not None:
                qual = f.get("reference_identification_qualifier", "")
                val = f.get("reference_identification", "")
                current_claim["references"][qual] = val
                if qual in ("1K", "EJ", "D9"):
                    current_claim["payer_claim_control_number"] = val

            elif seg_id == "DTP" and current_claim is not None:
                current_claim["service_date"] = f.get("date_time_period", "")

            elif seg_id == "STC":
                stc_info = cls._parse_stc_segment(f)
                if current_claim is not None:
                    current_claim["status_information"].append(stc_info)

                # Check if this STC indicates a request for documentation (Category R0-R5, A4 action)
                stc1 = f.get("health_care_claim_status_composite", {})
                cat_code = stc1.get("category_code", "") if isinstance(stc1, dict) else ""
                action_code = f.get("action_code", "")
                
                # Check for R-series (Requests for Additional Information) or status codes indicating documentation
                if cat_code.startswith("R") or action_code == "A4":
                    # Create or update attachment requirement
                    status_desc = stc1.get("category_description", "") if isinstance(stc1, dict) else ""
                    attachment_item = {
                        "claim_tracking_number": current_claim.get("claim_tracking_number", "") if current_claim else "",
                        "payer_claim_control_number": current_claim.get("payer_claim_control_number", "") if current_claim else "",
                        "patient_name": current_subscriber.get("subscriber_name", {}).get("name_last_or_organization", "") if current_subscriber else "",
                        "status_category_code": cat_code,
                        "status_category_description": status_desc or get_code_description("claim_status_category_code", cat_code) or "Request for Additional Information",
                        "status_code": stc1.get("status_code", "") if isinstance(stc1, dict) else "",
                        "action_code": action_code,
                        "action_description": get_code_description("action_code", action_code) or "",
                        "status_effective_date": f.get("status_information_effective_date", ""),
                        "submitted_charges": float(f.get("total_submitted_charges_for_claim", "0") or 0.0),
                    }
                    result["required_attachments"].append(attachment_item)

            elif seg_id == "PWK":
                pwk_type = f.get("attachment_report_type_code", "")
                trans_code = f.get("attachment_transmission_code", "")
                ctrl_num = f.get("attachment_control_number", "")

                pwk_entry = {
                    "attachment_report_type_code": pwk_type,
                    "attachment_report_type_description": get_code_description("attachment_report_type_code", pwk_type) or "",
                    "attachment_transmission_code": trans_code,
                    "attachment_transmission_description": get_code_description("attachment_transmission_code", trans_code) or "",
                    "attachment_control_number": ctrl_num,
                    "copies_needed": f.get("report_copies_needed", "1"),
                }

                if current_claim is not None:
                    current_claim["paperwork_requests"].append(pwk_entry)

                # Correlate and enrich required_attachments list
                # If an item exists for current claim, enrich it; otherwise add new entry
                matched = False
                for req in result["required_attachments"]:
                    if current_claim and req.get("claim_tracking_number") == current_claim.get("claim_tracking_number"):
                        req.update(pwk_entry)
                        matched = True
                        break

                if not matched:
                    result["required_attachments"].append({
                        "claim_tracking_number": current_claim.get("claim_tracking_number", "") if current_claim else "",
                        "payer_claim_control_number": current_claim.get("payer_claim_control_number", "") if current_claim else "",
                        "patient_name": current_subscriber.get("subscriber_name", {}).get("name_last_or_organization", "") if current_subscriber else "",
                        **pwk_entry
                    })

        return result

    @classmethod
    def _parse_stc_segment(cls, f: Dict[str, Any]) -> Dict[str, Any]:
        stc1 = f.get("health_care_claim_status_composite", {})
        action_code = f.get("action_code", "")
        return {
            "status_composite": stc1,
            "status_effective_date": f.get("status_information_effective_date", ""),
            "action_code": action_code,
            "action_description": get_code_description("action_code", action_code) or "",
            "total_submitted_charges": float(f.get("total_submitted_charges_for_claim", "0") or 0.0),
            "amount_paid": float(f.get("monetary_amount_paid", "0") or 0.0),
        }
