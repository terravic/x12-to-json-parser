"""
X12 837 (Health Care Claim - Professional & Institutional) Parser.
"""

from typing import Dict, List, Any, Optional
from ..engine.segment_parser import ParsedSegment
from ..engine.dictionary import get_code_description


class Claims837Parser:
    """Parses X12 837 claims (837P and 837I) into rich hierarchical JSON structures."""

    @classmethod
    def parse_837(cls, segments: List[ParsedSegment]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "transaction_type": "837",
            "transaction_description": "Health Care Claim",
            "submitter": {},
            "receiver": {},
            "billing_provider": {},
            "subscriber": {},
            "payer": {},
            "patient": {},
            "claims": [],
        }

        current_entity_loop = ""
        current_claim: Optional[Dict[str, Any]] = None
        current_service_line: Optional[Dict[str, Any]] = None

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
                    "claim_encounter_identifier": f.get("reference_identification", ""),
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

                if not current_claim:
                    if entity_code == "41":  # Submitter
                        result["submitter"] = entity_info
                        current_entity_loop = "submitter"
                    elif entity_code == "40":  # Receiver
                        result["receiver"] = entity_info
                        current_entity_loop = "receiver"
                    elif entity_code == "85":  # Billing Provider
                        result["billing_provider"] = entity_info
                        current_entity_loop = "billing_provider"
                    elif entity_code == "IL":  # Subscriber
                        result["subscriber"] = entity_info
                        current_entity_loop = "subscriber"
                    elif entity_code == "PR":  # Payer
                        result["payer"] = entity_info
                        current_entity_loop = "payer"
                    elif entity_code == "QC":  # Patient
                        result["patient"] = entity_info
                        current_entity_loop = "patient"
                else:
                    # Inside claim loop
                    if entity_code == "82":  # Rendering Provider
                        current_claim["rendering_provider"] = entity_info
                    elif entity_code == "DN":  # Referring Provider
                        current_claim["referring_provider"] = entity_info
                    elif entity_code == "77":  # Service Facility Location
                        current_claim["service_facility"] = entity_info

            elif seg_id == "N3":
                addr = {
                    "address_line_1": f.get("address_line_1", ""),
                    "address_line_2": f.get("address_line_2", ""),
                }
                if current_entity_loop == "billing_provider":
                    result["billing_provider"]["address"] = addr
                elif current_entity_loop == "subscriber":
                    result["subscriber"]["address"] = addr
                elif current_entity_loop == "patient":
                    result["patient"]["address"] = addr

            elif seg_id == "N4":
                geo = {
                    "city": f.get("city_name", ""),
                    "state": f.get("state_or_province_code", ""),
                    "postal_code": f.get("postal_code", ""),
                }
                if current_entity_loop == "billing_provider":
                    result["billing_provider"]["geographic_location"] = geo
                elif current_entity_loop == "subscriber":
                    result["subscriber"]["geographic_location"] = geo
                elif current_entity_loop == "patient":
                    result["patient"]["geographic_location"] = geo

            elif seg_id == "DMG":
                dmg = {
                    "date_of_birth": f.get("date_of_birth", ""),
                    "gender": f.get("gender_code", ""),
                }
                if current_entity_loop == "subscriber":
                    result["subscriber"]["demographics"] = dmg
                elif current_entity_loop == "patient":
                    result["patient"]["demographics"] = dmg

            elif seg_id == "CLM":
                charge_amt = f.get("total_claim_charge_amount", "0")
                current_claim = {
                    "claim_id": f.get("claim_submitters_identifier", ""),
                    "total_claim_charge_amount": float(charge_amt) if charge_amt else 0.0,
                    "claim_filing_indicator": f.get("claim_filing_indicator_code", ""),
                    "place_of_service": f.get("health_care_service_location_information", ""),
                    "signature_indicator": f.get("provider_or_supplier_signature_indicator", ""),
                    "assignment_indicator": f.get("assignment_or_plan_participation_code", ""),
                    "release_of_information": f.get("release_of_information_code", ""),
                    "dates": {},
                    "diagnoses": [],
                    "attachments": [],
                    "service_lines": [],
                }
                result["claims"].append(current_claim)
                current_service_line = None

            elif seg_id == "DTP" and current_claim is not None:
                qualifier = f.get("date_time_qualifier", "")
                date_val = f.get("date_time_period", "")
                if current_service_line is not None:
                    current_service_line["service_date"] = date_val
                    current_service_line["date_qualifier"] = qualifier
                else:
                    if qualifier == "472":
                        current_claim["dates"]["service_date"] = date_val
                    elif qualifier == "435":
                        current_claim["dates"]["admission_date"] = date_val
                    elif qualifier == "096":
                        current_claim["dates"]["discharge_date"] = date_val
                    else:
                        current_claim["dates"][f"date_{qualifier}"] = date_val

            elif seg_id == "HI" and current_claim is not None:
                for elem_k, elem_v in f.items():
                    if isinstance(elem_v, dict) and elem_v.get("code"):
                        current_claim["diagnoses"].append({
                            "diagnosis_type": elem_v.get("qualifier", ""),
                            "code": elem_v.get("code", ""),
                            "present_on_admission": elem_v.get("present_on_admission", ""),
                        })

            elif seg_id == "PWK" and current_claim is not None:
                pwk_type = f.get("attachment_report_type_code", "")
                current_claim["attachments"].append({
                    "report_type_code": pwk_type,
                    "report_type_description": get_code_description("attachment_report_type_code", pwk_type) or "",
                    "transmission_code": f.get("attachment_transmission_code", ""),
                    "transmission_description": get_code_description("attachment_transmission_code", f.get("attachment_transmission_code", "")) or "",
                    "attachment_control_number": f.get("attachment_control_number", ""),
                })

            elif seg_id == "LX" and current_claim is not None:
                current_service_line = {
                    "line_number": f.get("assigned_number", str(len(current_claim["service_lines"]) + 1)),
                    "procedure": {},
                    "charge_amount": 0.0,
                    "unit_count": 1.0,
                    "service_date": "",
                }
                current_claim["service_lines"].append(current_service_line)

            elif seg_id in ("SV1", "SV2") and current_service_line is not None:
                proc = f.get("composite_medical_procedure_identifier", {})
                charge = f.get("line_item_charge_amount", "0")
                units = f.get("service_unit_count", "1")
                current_service_line["procedure"] = proc
                current_service_line["charge_amount"] = float(charge) if charge else 0.0
                current_service_line["unit_count"] = float(units) if units else 1.0
                if seg_id == "SV1":
                    current_service_line["place_of_service"] = f.get("place_of_service_code", "")
                elif seg_id == "SV2":
                    current_service_line["revenue_code"] = f.get("revenue_code", "")

        return result
