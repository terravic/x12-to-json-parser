"""
Base X12 EDI Engine and Master Orchestrator.

Handles full envelope validation (ISA/GS/ST/SE/GE/IEA), multi-group/multi-transaction batches,
hierarchical loop building, and dispatch to specialized transaction parsers.
"""

import json
from typing import Dict, List, Any, Optional, Union
from .tokenizer import X12Tokenizer, RawSegment, X12Delimiters
from .segment_parser import ParsedSegment
from .loop_builder import LoopBuilder
from ..transaction_parsers.eligibility_270_271 import EligibilityParser
from ..transaction_parsers.prior_auth_278 import PriorAuthParser
from ..transaction_parsers.claims_837 import Claims837Parser
from ..transaction_parsers.remittance_835 import Remittance835Parser
from ..transaction_parsers.status_request_277 import StatusRequest277Parser
from ..transaction_parsers.attachment_275 import Attachment275Parser


class X12Parser:
    """Master X12-to-JSON Parser."""

    def __init__(self, raw_content: str):
        self.raw_content = raw_content.strip()
        self.tokenizer = X12Tokenizer(self.raw_content)
        self.delimiters = self.tokenizer.delimiters
        self.raw_segments = self.tokenizer.tokenize()
        self.parsed_segments = [
            ParsedSegment(s, self.delimiters) for s in self.raw_segments
        ]

    @classmethod
    def parse(cls, raw_content: str) -> Dict[str, Any]:
        """Convenience method to parse raw X12 content into structured JSON dict."""
        instance = cls(raw_content)
        return instance.to_dict()

    @classmethod
    def to_json_string(cls, raw_content: str, indent: int = 2) -> str:
        """Parse and serialize to formatted JSON string."""
        data = cls.parse(raw_content)
        return json.dumps(data, indent=indent, default=str)

    @classmethod
    def generate_dashboard(
        cls,
        raw_or_parsed: Union[str, Dict[str, Any]],
        output_path: Optional[str] = None,
        raw_x12: str = "",
        title: str = "EDI X12 Parsed Transaction Dashboard"
    ) -> str:
        """
        Generate an interactive standalone HTML visual dashboard for any X12 raw text or parsed dictionary.
        Optionally save to output_path if provided.
        """
        from ..ui.dashboard_generator import generate_html_dashboard, save_html_dashboard

        if isinstance(raw_or_parsed, dict):
            parsed_data = raw_or_parsed
            x12_str = raw_x12
        else:
            x12_str = str(raw_or_parsed)
            parsed_data = cls.parse(x12_str)

        if output_path:
            return save_html_dashboard(parsed_data, output_path=output_path, raw_x12=x12_str, title=title)
        return generate_html_dashboard(parsed_data, raw_x12=x12_str, title=title)

    def to_dict(self) -> Dict[str, Any]:
        """Execute full parsing pipeline and return standardized output schema."""
        interchange: Dict[str, Any] = {
            "delimiters": self.delimiters.to_dict(),
            "interchange_header": {},
            "functional_groups": [],
            "interchange_trailer": {},
            "summary": {
                "total_segments_count": len(self.parsed_segments),
                "total_functional_groups_count": 0,
                "total_transaction_sets_count": 0,
            }
        }

        current_group: Optional[Dict[str, Any]] = None
        current_tx: Optional[Dict[str, Any]] = None
        current_tx_segments: List[ParsedSegment] = []

        for seg in self.parsed_segments:
            seg_id = seg.segment_id
            f = seg.fields

            if seg_id == "ISA":
                interchange["interchange_header"] = seg.to_dict()

            elif seg_id == "IEA":
                interchange["interchange_trailer"] = seg.to_dict()

            elif seg_id == "GS":
                current_group = {
                    "functional_group_header": seg.to_dict(),
                    "functional_identifier_code": f.get("functional_identifier_code", ""),
                    "sender_code": f.get("application_sender_code", ""),
                    "receiver_code": f.get("application_receiver_code", ""),
                    "group_control_number": f.get("group_control_number", ""),
                    "version": f.get("version_release_industry_identifier_code", ""),
                    "transaction_sets": [],
                    "functional_group_trailer": {},
                }
                interchange["functional_groups"].append(current_group)
                interchange["summary"]["total_functional_groups_count"] += 1

            elif seg_id == "GE":
                if current_group is not None:
                    current_group["functional_group_trailer"] = seg.to_dict()
                    current_group = None

            elif seg_id == "ST":
                tx_type = f.get("transaction_set_identifier_code", "")
                tx_ctrl = f.get("transaction_set_control_number", "")
                tx_convention = f.get("implementation_convention_reference", "")

                current_tx = {
                    "transaction_type": tx_type,
                    "transaction_set_control_number": tx_ctrl,
                    "implementation_convention_reference": tx_convention,
                    "transaction_header": seg.to_dict(),
                    "parsed_transaction": {},
                    "hierarchical_loops": {},
                    "segments": [],
                    "transaction_trailer": {},
                }
                current_tx_segments = [seg]

                if current_group is not None:
                    current_group["transaction_sets"].append(current_tx)
                else:
                    # Isolated transaction set without GS
                    if not interchange["functional_groups"]:
                        temp_group = {
                            "functional_group_header": {},
                            "transaction_sets": [current_tx],
                            "functional_group_trailer": {},
                        }
                        interchange["functional_groups"].append(temp_group)
                    else:
                        interchange["functional_groups"][-1]["transaction_sets"].append(current_tx)

                interchange["summary"]["total_transaction_sets_count"] += 1

            elif seg_id == "SE":
                if current_tx is not None:
                    current_tx_segments.append(seg)
                    current_tx["transaction_trailer"] = seg.to_dict()
                    current_tx["segments"] = [s.to_dict() for s in current_tx_segments]

                    # Parse transaction business logic
                    tx_type = current_tx["transaction_type"]
                    current_tx["parsed_transaction"] = self._parse_transaction_payload(tx_type, current_tx_segments)
                    current_tx["hierarchical_loops"] = LoopBuilder.build_transaction_tree(tx_type, current_tx_segments)

                    current_tx = None
                    current_tx_segments = []

            else:
                if current_tx is not None:
                    current_tx_segments.append(seg)

        # If file ended without explicit SE (e.g. fragment), parse remaining segments
        if current_tx is not None and current_tx_segments:
            tx_type = current_tx["transaction_type"]
            current_tx["segments"] = [s.to_dict() for s in current_tx_segments]
            current_tx["parsed_transaction"] = self._parse_transaction_payload(tx_type, current_tx_segments)
            current_tx["hierarchical_loops"] = LoopBuilder.build_transaction_tree(tx_type, current_tx_segments)

        return interchange

    def _parse_transaction_payload(self, tx_type: str, segments: List[ParsedSegment]) -> Dict[str, Any]:
        """Route to specialized transaction parser."""
        if tx_type == "270":
            return EligibilityParser.parse_270(segments)
        elif tx_type == "271":
            return EligibilityParser.parse_271(segments)
        elif tx_type == "278":
            return PriorAuthParser.parse_278(segments)
        elif tx_type == "837":
            return Claims837Parser.parse_837(segments)
        elif tx_type == "835":
            return Remittance835Parser.parse_835(segments)
        elif tx_type == "277":
            return StatusRequest277Parser.parse_277(segments)
        elif tx_type == "275":
            return Attachment275Parser.parse_275(segments)
        else:
            return {
                "transaction_type": tx_type,
                "note": f"Generic parser for transaction {tx_type}",
                "segments_count": len(segments),
            }
