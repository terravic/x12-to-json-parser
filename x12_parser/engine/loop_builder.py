"""
X12 Hierarchical Loop Builder.

Organizes parsed X12 segments into standard hierarchical loops
(e.g., HL hierarchical levels, Loop 2000, 2010, 2100, 2300, 2400)
based on X12 5010 Implementation Guides.
"""

from typing import List, Dict, Any, Optional
from .segment_parser import ParsedSegment


class LoopNode:
    """Represents a loop container in the X12 hierarchy."""

    def __init__(self, loop_id: str, loop_name: str = ""):
        self.loop_id = loop_id
        self.loop_name = loop_name
        self.segments: List[ParsedSegment] = []
        self.sub_loops: List["LoopNode"] = []
        self.attributes: Dict[str, Any] = {}

    def add_segment(self, segment: ParsedSegment) -> None:
        self.segments.append(segment)

    def add_sub_loop(self, sub_loop: "LoopNode") -> None:
        self.sub_loops.append(sub_loop)

    def get_first_segment(self, segment_id: str) -> Optional[ParsedSegment]:
        for seg in self.segments:
            if seg.segment_id == segment_id:
                return seg
        return None

    def get_segments(self, segment_id: str) -> List[ParsedSegment]:
        return [seg for seg in self.segments if seg.segment_id == segment_id]

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "loop_id": self.loop_id,
            "loop_name": self.loop_name,
        }
        if self.attributes:
            res["attributes"] = self.attributes

        res["segments"] = [s.to_dict() for s in self.segments]

        if self.sub_loops:
            # Group subloops by loop_id or return as list
            res["sub_loops"] = [sub.to_dict() for sub in self.sub_loops]

        return res


class LoopBuilder:
    """Builds hierarchical loop structures for X12 transaction sets."""

    @classmethod
    def build_transaction_tree(
        cls,
        tx_type: str,
        segments: List[ParsedSegment],
    ) -> Dict[str, Any]:
        """
        Build loop hierarchy based on transaction type (e.g., 837, 835, 270, 271, 277, 275, 278).
        """
        root = LoopNode("TRANSACTION", f"Transaction Set {tx_type}")
        
        # Build HL (Hierarchical Level) index or state-machine loop grouping
        has_hl = any(s.segment_id == "HL" for s in segments)
        
        if has_hl:
            return cls._build_hl_hierarchy(tx_type, segments)
        else:
            return cls._build_non_hl_hierarchy(tx_type, segments)

    @classmethod
    def _build_hl_hierarchy(cls, tx_type: str, segments: List[ParsedSegment]) -> Dict[str, Any]:
        """Group segments by HL (Hierarchical Level) parents and child subloops."""
        header_segments: List[ParsedSegment] = []
        hl_nodes: List[Dict[str, Any]] = []
        current_hl: Optional[Dict[str, Any]] = None
        trailer_segments: List[ParsedSegment] = []

        in_trailer = False

        for seg in segments:
            seg_id = seg.segment_id
            
            if seg_id in ("ST", "BHT", "BGN", "CUR"):
                header_segments.append(seg)
                continue

            if seg_id in ("SE",):
                in_trailer = True
                trailer_segments.append(seg)
                continue

            if in_trailer:
                trailer_segments.append(seg)
                continue

            if seg_id == "HL":
                hl_id = seg.fields.get("hierarchical_id_number", "")
                parent_id = seg.fields.get("hierarchical_parent_id_number", "")
                level_code = seg.fields.get("hierarchical_level_code", "")
                child_code = seg.fields.get("hierarchical_child_code", "")

                current_hl = {
                    "hl_id": hl_id,
                    "parent_id": parent_id,
                    "level_code": level_code,
                    "child_code": child_code,
                    "hl_segment": seg.to_dict(),
                    "segments": [],
                    "child_hls": [],
                }
                hl_nodes.append(current_hl)
                continue

            if current_hl is not None:
                current_hl["segments"].append(seg)
            else:
                header_segments.append(seg)

        # Build tree of HLs using parent_id
        hl_map: Dict[str, Dict[str, Any]] = {}
        root_hls: List[Dict[str, Any]] = []

        for hl in hl_nodes:
            hl_map[str(hl["hl_id"])] = hl

        for hl in hl_nodes:
            pid = str(hl.get("parent_id", "")).strip()
            if pid and pid in hl_map:
                hl_map[pid]["child_hls"].append(hl)
            else:
                root_hls.append(hl)

        return {
            "transaction_type": tx_type,
            "header_segments": [s.to_dict() for s in header_segments],
            "hierarchical_loops": root_hls,
            "trailer_segments": [s.to_dict() for s in trailer_segments],
        }

    @classmethod
    def _build_non_hl_hierarchy(cls, tx_type: str, segments: List[ParsedSegment]) -> Dict[str, Any]:
        """Group non-HL transactions (like 835 Remittance) into structured loops."""
        header_segments: List[ParsedSegment] = []
        detail_loops: List[Dict[str, Any]] = []
        trailer_segments: List[ParsedSegment] = []
        current_claim_loop: Optional[Dict[str, Any]] = None
        current_service_loop: Optional[Dict[str, Any]] = None

        for seg in segments:
            seg_id = seg.segment_id
            
            if seg_id in ("ST", "BPR", "TRN", "CUR", "REF", "DTM") and not current_claim_loop:
                header_segments.append(seg)
                continue

            if seg_id in ("N1", "N3", "N4", "PER") and not current_claim_loop:
                header_segments.append(seg)
                continue

            # 835 Claim Loop trigger: CLP
            if seg_id == "CLP":
                current_claim_loop = {
                    "loop_id": "2100",
                    "loop_name": "Claim Payment Information",
                    "claim_payment": seg.to_dict(),
                    "segments": [],
                    "service_lines": [],
                }
                detail_loops.append(current_claim_loop)
                current_service_loop = None
                continue

            # 835 Service Line trigger: SVC
            if seg_id == "SVC" and current_claim_loop is not None:
                current_service_loop = {
                    "loop_id": "2110",
                    "loop_name": "Service Payment Information",
                    "service_payment": seg.to_dict(),
                    "segments": [],
                }
                current_claim_loop["service_lines"].append(current_service_loop)
                continue

            if seg_id in ("PLB", "SE"):
                trailer_segments.append(seg)
                current_claim_loop = None
                current_service_loop = None
                continue

            if current_service_loop is not None:
                current_service_loop["segments"].append(seg.to_dict())
            elif current_claim_loop is not None:
                current_claim_loop["segments"].append(seg.to_dict())
            else:
                header_segments.append(seg)

        return {
            "transaction_type": tx_type,
            "header_segments": [s.to_dict() for s in header_segments],
            "claim_loops": detail_loops,
            "trailer_segments": [s.to_dict() for s in trailer_segments],
        }
