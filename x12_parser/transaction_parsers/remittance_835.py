"""
X12 835 (Health Care Claim Payment / Electronic Remittance Advice - ERA) Parser.
"""

from typing import Dict, List, Any, Optional
from ..engine.segment_parser import ParsedSegment
from ..engine.dictionary import get_code_description


class Remittance835Parser:
    """Parses X12 835 Remittance Advice into structured payment and adjustment objects."""

    @classmethod
    def parse_835(cls, segments: List[ParsedSegment]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "transaction_type": "835",
            "transaction_description": "Health Care Claim Payment / Advice (ERA)",
            "financial_information": {},
            "reassociation_trace": {},
            "payer": {},
            "payee": {},
            "claims": [],
            "provider_adjustments": [],
            "summary": {
                "total_claims_count": 0,
                "total_charge_amount": 0.0,
                "total_payment_amount": 0.0,
                "total_patient_responsibility": 0.0,
                "total_adjustment_amount": 0.0,
            }
        }

        current_claim: Optional[Dict[str, Any]] = None
        current_service_line: Optional[Dict[str, Any]] = None
        current_entity_code = ""

        for seg in segments:
            seg_id = seg.segment_id
            f = seg.fields

            if seg_id == "BPR":
                pay_amt = f.get("total_actual_provider_payment_amount", "0")
                result["financial_information"] = {
                    "transaction_handling_code": f.get("transaction_handling_code", ""),
                    "total_payment_amount": float(pay_amt) if pay_amt else 0.0,
                    "credit_debit_flag": f.get("credit_debit_flag_code", ""),
                    "payment_method": f.get("payment_method_code", ""),
                    "payment_effective_date": f.get("check_or_eft_effective_date", ""),
                    "sender_bank_routing_number": f.get("sender_bank_transit_routing_number", ""),
                    "receiver_bank_account_number": f.get("receiver_bank_account_number", ""),
                }

            elif seg_id == "TRN":
                result["reassociation_trace"] = {
                    "trace_type": f.get("trace_type_code", ""),
                    "check_or_eft_trace_number": f.get("reference_identification_trace_number", ""),
                    "originating_company_id": f.get("originating_company_identifier", ""),
                }

            elif seg_id == "N1":
                entity_code = f.get("entity_identifier_code", "")
                current_entity_code = entity_code
                entity_info = {
                    "entity_identifier_code": entity_code,
                    "name": f.get("name_last_or_organization_name", ""),
                    "identification_code_qualifier": f.get("identification_code_qualifier", ""),
                    "identification_code": f.get("identification_code", ""),
                }
                if entity_code == "PR":  # Payer
                    result["payer"] = entity_info
                elif entity_code == "PE":  # Payee
                    result["payee"] = entity_info

            elif seg_id == "N3":
                addr = {"address_line_1": f.get("address_line_1", ""), "address_line_2": f.get("address_line_2", "")}
                if current_entity_code == "PR":
                    result["payer"]["address"] = addr
                elif current_entity_code == "PE":
                    result["payee"]["address"] = addr

            elif seg_id == "N4":
                geo = {"city": f.get("city_name", ""), "state": f.get("state_or_province_code", ""), "postal_code": f.get("postal_code", "")}
                if current_entity_code == "PR":
                    result["payer"]["geographic_location"] = geo
                elif current_entity_code == "PE":
                    result["payee"]["geographic_location"] = geo

            elif seg_id == "CLP":
                charge_amt = float(f.get("total_claim_charge_amount", "0") or 0.0)
                pay_amt = float(f.get("claim_payment_amount", "0") or 0.0)
                patient_resp = float(f.get("patient_responsibility_amount", "0") or 0.0)
                status_code = f.get("claim_status_code", "")

                current_claim = {
                    "patient_control_number": f.get("claim_submitters_identifier", ""),
                    "claim_status_code": status_code,
                    "claim_status_description": get_code_description("claim_status_code", status_code) or "",
                    "total_claim_charge_amount": charge_amt,
                    "claim_payment_amount": pay_amt,
                    "patient_responsibility_amount": patient_resp,
                    "payer_claim_control_number": f.get("payer_claim_control_number", ""),
                    "claim_filing_indicator": f.get("claim_filing_indicator_code", ""),
                    "patient": {},
                    "insured": {},
                    "service_provider": {},
                    "adjustments": [],
                    "service_lines": [],
                }
                result["claims"].append(current_claim)
                current_service_line = None

                # Summary updates
                result["summary"]["total_claims_count"] += 1
                result["summary"]["total_charge_amount"] += charge_amt
                result["summary"]["total_payment_amount"] += pay_amt
                result["summary"]["total_patient_responsibility"] += patient_resp

            elif seg_id == "NM1" and current_claim is not None:
                entity_code = f.get("entity_identifier_code", "")
                entity_info = {
                    "name_last_or_organization": f.get("name_last_or_organization_name", ""),
                    "name_first": f.get("name_first", ""),
                    "identification_code": f.get("identification_code", ""),
                }
                if entity_code == "QC":
                    current_claim["patient"] = entity_info
                elif entity_code == "IL":
                    current_claim["insured"] = entity_info
                elif entity_code == "82":
                    current_claim["service_provider"] = entity_info

            elif seg_id == "CAS":
                adjustments = cls._parse_cas_segment(f)
                for adj in adjustments:
                    result["summary"]["total_adjustment_amount"] += adj.get("adjustment_amount", 0.0)

                if current_service_line is not None:
                    current_service_line["adjustments"].extend(adjustments)
                elif current_claim is not None:
                    current_claim["adjustments"].extend(adjustments)

            elif seg_id == "SVC" and current_claim is not None:
                line_charge = float(f.get("line_item_charge_amount", "0") or 0.0)
                line_pay = float(f.get("line_item_provider_payment_amount", "0") or 0.0)
                units = float(f.get("units_of_service_paid_count", "1") or 1.0)

                current_service_line = {
                    "line_item_number": len(current_claim["service_lines"]) + 1,
                    "procedure": f.get("composite_medical_procedure_identifier", {}),
                    "line_charge_amount": line_charge,
                    "line_payment_amount": line_pay,
                    "units_paid": units,
                    "revenue_code": f.get("national_uniform_billing_committee_revenue_code", ""),
                    "adjustments": [],
                }
                current_claim["service_lines"].append(current_service_line)

            elif seg_id == "PLB":
                adj_id = f.get("adjustment_identifier_1", "")
                adj_amt = float(f.get("provider_adjustment_amount_1", "0") or 0.0)
                result["provider_adjustments"].append({
                    "provider_identifier": f.get("provider_identifier", ""),
                    "fiscal_period_date": f.get("fiscal_period_date", ""),
                    "adjustment_identifier": adj_id,
                    "adjustment_amount": adj_amt,
                })

        return result

    @classmethod
    def _parse_cas_segment(cls, f: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse multiple adjustment reason codes and amounts inside a single CAS segment."""
        group_code = f.get("claim_adjustment_group_code", "")
        group_desc = get_code_description("claim_adjustment_group_code", group_code) or group_code

        adjustments: List[Dict[str, Any]] = []
        for i in range(1, 7):
            reason_code = f.get(f"claim_adjustment_reason_code_{i}", "")
            amount_str = f.get(f"adjustment_amount_{i}", "")
            qty_str = f.get(f"adjustment_quantity_{i}", "")

            if reason_code or amount_str:
                amt = float(amount_str) if amount_str else 0.0
                adjustments.append({
                    "group_code": group_code,
                    "group_description": group_desc,
                    "reason_code": reason_code,
                    "adjustment_amount": amt,
                    "quantity": float(qty_str) if qty_str else None,
                })

        return adjustments
