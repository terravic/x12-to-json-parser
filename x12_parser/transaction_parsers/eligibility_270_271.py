"""
X12 270 (Eligibility Inquiry) and 271 (Eligibility Response) Transaction Parsers.
"""

from typing import Dict, List, Any, Optional
from ..engine.segment_parser import ParsedSegment
from ..engine.dictionary import get_code_description


class EligibilityParser:
    """Parses 270 and 271 transactions into clean healthcare eligibility structures."""

    @classmethod
    def parse_270(cls, segments: List[ParsedSegment]) -> Dict[str, Any]:
        """Parse 270 Health Care Eligibility Benefit Inquiry."""
        result: Dict[str, Any] = {
            "transaction_type": "270",
            "transaction_description": "Health Care Eligibility Benefit Inquiry",
            "information_source": {},
            "information_receiver": {},
            "subscriber": {},
            "dependents": [],
            "inquiries": [],
        }

        current_entity = ""
        current_subscriber: Dict[str, Any] = {"inquiries": []}
        current_dependent: Optional[Dict[str, Any]] = None

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
                entity_name = cls._parse_nm1_name(f)
                if entity_code == "PR":  # Payer / Information Source
                    result["information_source"] = entity_name
                    current_entity = "source"
                elif entity_code in ("1P", "FA", "85"):  # Provider / Information Receiver
                    result["information_receiver"] = entity_name
                    current_entity = "receiver"
                elif entity_code == "IL":  # Insured / Subscriber
                    current_subscriber.update(entity_name)
                    current_entity = "subscriber"
                elif entity_code == "03":  # Dependent
                    current_dependent = entity_name
                    current_dependent["inquiries"] = []
                    result["dependents"].append(current_dependent)
                    current_entity = "dependent"

            elif seg_id == "DMG":
                dmg_info = {
                    "date_of_birth": f.get("date_of_birth", ""),
                    "gender": f.get("gender_code", ""),
                }
                if current_entity == "subscriber":
                    current_subscriber["demographics"] = dmg_info
                elif current_entity == "dependent" and current_dependent:
                    current_dependent["demographics"] = dmg_info

            elif seg_id == "EQ":
                service_type = f.get("service_type_code", "")
                inquiry = {
                    "service_type_code": service_type,
                    "service_type_description": get_code_description("service_type_code", service_type) or "",
                    "procedure": f.get("composite_medical_procedure_identifier", {}),
                    "coverage_level_code": f.get("coverage_level_code", ""),
                    "insurance_type_code": f.get("insurance_type_code", ""),
                }
                if current_entity == "dependent" and current_dependent:
                    current_dependent["inquiries"].append(inquiry)
                else:
                    current_subscriber["inquiries"].append(inquiry)
                result["inquiries"].append(inquiry)

        result["subscriber"] = current_subscriber
        return result

    @classmethod
    def parse_271(cls, segments: List[ParsedSegment]) -> Dict[str, Any]:
        """Parse 271 Health Care Eligibility Benefit Response."""
        result: Dict[str, Any] = {
            "transaction_type": "271",
            "transaction_description": "Health Care Eligibility Benefit Response",
            "information_source": {},
            "information_receiver": {},
            "subscriber": {},
            "dependents": [],
            "eligibility_benefits": [],
        }

        current_entity = ""
        current_subscriber: Dict[str, Any] = {"eligibility_benefits": []}
        current_dependent: Optional[Dict[str, Any]] = None

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
                entity_name = cls._parse_nm1_name(f)
                if entity_code == "PR":  # Payer
                    result["information_source"] = entity_name
                    current_entity = "source"
                elif entity_code in ("1P", "FA", "85"):  # Provider
                    result["information_receiver"] = entity_name
                    current_entity = "receiver"
                elif entity_code == "IL":  # Subscriber
                    current_subscriber.update(entity_name)
                    current_entity = "subscriber"
                elif entity_code == "03":  # Dependent
                    current_dependent = entity_name
                    current_dependent["eligibility_benefits"] = []
                    result["dependents"].append(current_dependent)
                    current_entity = "dependent"

            elif seg_id == "DMG":
                dmg_info = {
                    "date_of_birth": f.get("date_of_birth", ""),
                    "gender": f.get("gender_code", ""),
                }
                if current_entity == "subscriber":
                    current_subscriber["demographics"] = dmg_info
                elif current_entity == "dependent" and current_dependent:
                    current_dependent["demographics"] = dmg_info

            elif seg_id == "EB":
                eb_code = f.get("eligibility_or_benefit_information_code", "")
                srv_code = f.get("service_type_code", "")
                amount = f.get("monetary_amount", "")
                percent = f.get("percent_decimal", "")
                
                benefit = {
                    "eligibility_code": eb_code,
                    "eligibility_description": get_code_description("eligibility_or_benefit_information_code", eb_code) or "",
                    "coverage_level_code": f.get("coverage_level_code", ""),
                    "service_type_code": srv_code,
                    "service_type_description": get_code_description("service_type_code", srv_code) or "",
                    "insurance_type_code": f.get("insurance_type_code", ""),
                    "plan_coverage_description": f.get("plan_coverage_description", ""),
                    "monetary_amount": float(amount) if amount else None,
                    "percent": float(percent) if percent else None,
                    "time_period_qualifier": f.get("time_period_qualifier", ""),
                    "in_plan_network_indicator": f.get("in_plan_network_indicator", ""),
                    "authorization_required": f.get("authorization_or_certification_required", ""),
                }

                if current_entity == "dependent" and current_dependent:
                    current_dependent["eligibility_benefits"].append(benefit)
                else:
                    current_subscriber["eligibility_benefits"].append(benefit)
                result["eligibility_benefits"].append(benefit)

        result["subscriber"] = current_subscriber
        return result

    @staticmethod
    def _parse_nm1_name(f: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "entity_identifier_code": f.get("entity_identifier_code", ""),
            "entity_type": "Person" if f.get("entity_type_qualifier") == "1" else "Non-Person/Organization",
            "name_last_or_organization": f.get("name_last_or_organization_name", ""),
            "name_first": f.get("name_first", ""),
            "name_middle": f.get("name_middle", ""),
            "identification_code_qualifier": f.get("identification_code_qualifier", ""),
            "identification_code": f.get("identification_code", ""),
        }
