"""
X12 Tokenizer and Delimiter Detection Engine.

Handles automatic detection of element, component, repetition, and segment delimiters
from the ISA interchange control header, with support for embedded binary/XML payloads (BDS/BIN).
"""

from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class X12Delimiters:
    element_separator: str = "*"
    component_separator: str = ":"
    segment_terminator: str = "~"
    repetition_separator: str = "^"

    def to_dict(self) -> Dict[str, str]:
        return {
            "element_separator": self.element_separator,
            "component_separator": self.component_separator,
            "segment_terminator": self.segment_terminator,
            "repetition_separator": self.repetition_separator,
        }


@dataclass
class RawSegment:
    segment_id: str
    elements: List[str] = field(default_factory=list)
    line_number: int = 0
    raw_text: str = ""

    def get_element(self, index: int, default: str = "") -> str:
        """Get element at 1-based index."""
        if 1 <= index <= len(self.elements):
            return self.elements[index - 1]
        return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "elements": self.elements,
            "line_number": self.line_number,
        }


class X12Tokenizer:
    """Tokenizes raw X12 EDI text into structured RawSegment instances."""

    def __init__(self, raw_content: str):
        self.raw_content = raw_content.strip()
        self.delimiters = self.detect_delimiters(self.raw_content)

    @classmethod
    def detect_delimiters(cls, content: str) -> X12Delimiters:
        """
        Detect delimiters from ISA header.
        Standard ISA:
        - Position 3: Element delimiter (e.g. '*')
        - Position 82: Repetition separator (ISA11) (e.g. '^')
        - Position 104: Component separator (ISA16) (e.g. ':')
        - Position 105: Segment terminator (e.g. '~' or '\n')
        """
        content_stripped = content.strip()
        if content_stripped.startswith("ISA"):
            elem_sep = content_stripped[3]
            # Split first segment by element separator to inspect elements
            # Look for 106-character standard ISA or split
            if len(content_stripped) >= 106 and content_stripped[0:3] == "ISA":
                elem_sep = content_stripped[3]
                rep_sep = content_stripped[82]
                comp_sep = content_stripped[104]
                seg_term = content_stripped[105]
                # If segment terminator is \r or \n, normalize
                if seg_term in ("\r", "\n") and len(content_stripped) > 106 and content_stripped[106] == "\n":
                    seg_term = content_stripped[105:107]
                return X12Delimiters(
                    element_separator=elem_sep,
                    component_separator=comp_sep,
                    segment_terminator=seg_term,
                    repetition_separator=rep_sep,
                )
            else:
                # Fallback delimiter search
                elem_sep = content_stripped[3]
                # find first segment end
                idx = 3
                parts = []
                while idx < len(content_stripped) and len(parts) < 16:
                    next_idx = content_stripped.find(elem_sep, idx)
                    if next_idx == -1:
                        break
                    parts.append(content_stripped[idx:next_idx])
                    idx = next_idx + 1
                comp_sep = ":"
                seg_term = "~"
                rep_sep = "^"
                if len(parts) >= 16:
                    comp_sep = parts[15][0] if len(parts[15]) > 0 else ":"
                return X12Delimiters(
                    element_separator=elem_sep,
                    component_separator=comp_sep,
                    segment_terminator=seg_term,
                    repetition_separator=rep_sep,
                )

        # Fallback defaults if no ISA (e.g. isolated transaction set)
        return X12Delimiters(
            element_separator="*",
            component_separator=":",
            segment_terminator="~",
            repetition_separator="^",
        )

    def tokenize(self) -> List[RawSegment]:
        """Tokenize entire X12 document into RawSegment list, handling embedded BDS/BIN payloads."""
        segments: List[RawSegment] = []
        seg_term = self.delimiters.segment_terminator
        elem_sep = self.delimiters.element_separator

        # Handle special segment terminators (e.g. ~ followed by \n)
        raw = self.raw_content
        i = 0
        n = len(raw)
        seg_line = 1

        while i < n:
            # Skip leading newlines/whitespace before segment start
            while i < n and raw[i] in "\r\n\t ":
                if raw[i] == "\n":
                    seg_line += 1
                i += 1
            if i >= n:
                break

            # Look ahead for segment ID
            seg_start = i
            # Check if this is BDS or BIN segment
            # BDS format: BDS*filter*length*payload~
            # BIN format: BIN*length*payload~
            prefix_check = raw[i:min(i+4, n)]
            
            if prefix_check.startswith("BDS" + elem_sep) or prefix_check.startswith("BIN" + elem_sep):
                # Binary/payload segment handling
                is_bds = prefix_check.startswith("BDS")
                # Parse the initial elements to get the length if specified
                next_term = raw.find(seg_term, i)
                # First let's check if the payload contains the segment terminator or not
                # Let's parse prefix
                first_elem_end = raw.find(elem_sep, i)
                seg_id = raw[i:first_elem_end]
                
                # Check elements
                elements: List[str] = []
                curr_pos = first_elem_end + 1
                
                if is_bds:
                    # BDS has: BDS*filter_id*length*payload
                    # find filter_id
                    filter_end = raw.find(elem_sep, curr_pos)
                    if filter_end != -1:
                        filter_id = raw[curr_pos:filter_end]
                        elements.append(filter_id)
                        curr_pos = filter_end + 1
                        
                        # find length
                        len_end = raw.find(elem_sep, curr_pos)
                        if len_end != -1:
                            len_str = raw[curr_pos:len_end]
                            elements.append(len_str)
                            curr_pos = len_end + 1
                            
                            # Now payload is at curr_pos.
                            # Length could be integer byte count
                            payload_len = None
                            try:
                                payload_len = int(len_str.strip())
                            except ValueError:
                                payload_len = None
                            
                            if payload_len is not None and payload_len > 0 and curr_pos + payload_len <= n:
                                payload = raw[curr_pos:curr_pos + payload_len]
                                elements.append(payload)
                                curr_pos += payload_len
                                # Find following segment terminator
                                term_idx = raw.find(seg_term, curr_pos)
                                if term_idx != -1:
                                    i = term_idx + len(seg_term)
                                else:
                                    i = n
                            else:
                                # Find next segment terminator that is followed by a valid next segment or end
                                # Or find closing tag </ClinicalDocument> or next segment like 'SE*' / 'GE*' / etc.
                                term_idx = self._find_payload_segment_end(raw, curr_pos, seg_term, elem_sep)
                                payload = raw[curr_pos:term_idx]
                                elements.append(payload)
                                i = term_idx + len(seg_term)
                        else:
                            term_idx = raw.find(seg_term, curr_pos)
                            if term_idx == -1: term_idx = n
                            elements.append(raw[curr_pos:term_idx])
                            i = term_idx + len(seg_term)
                    else:
                        term_idx = raw.find(seg_term, curr_pos)
                        if term_idx == -1: term_idx = n
                        elements.append(raw[curr_pos:term_idx])
                        i = term_idx + len(seg_term)
                else:
                    # BIN has: BIN*length*payload
                    len_end = raw.find(elem_sep, curr_pos)
                    if len_end != -1:
                        len_str = raw[curr_pos:len_end]
                        elements.append(len_str)
                        curr_pos = len_end + 1
                        payload_len = None
                        try:
                            payload_len = int(len_str.strip())
                        except ValueError:
                            payload_len = None
                        if payload_len is not None and payload_len > 0 and curr_pos + payload_len <= n:
                            payload = raw[curr_pos:curr_pos + payload_len]
                            elements.append(payload)
                            curr_pos += payload_len
                            term_idx = raw.find(seg_term, curr_pos)
                            i = term_idx + len(seg_term) if term_idx != -1 else n
                        else:
                            term_idx = self._find_payload_segment_end(raw, curr_pos, seg_term, elem_sep)
                            elements.append(raw[curr_pos:term_idx])
                            i = term_idx + len(seg_term)
                    else:
                        term_idx = raw.find(seg_term, curr_pos)
                        if term_idx == -1: term_idx = n
                        elements.append(raw[curr_pos:term_idx])
                        i = term_idx + len(seg_term)
                
                raw_seg_text = raw[seg_start:i]
                segments.append(RawSegment(
                    segment_id=seg_id,
                    elements=elements,
                    line_number=seg_line,
                    raw_text=raw_seg_text.strip()
                ))
                continue

            # Standard segment
            term_pos = raw.find(seg_term, i)
            if term_pos == -1:
                seg_text = raw[i:]
                i = n
            else:
                seg_text = raw[i:term_pos]
                i = term_pos + len(seg_term)

            seg_text_clean = seg_text.strip("\r\n ")
            if not seg_text_clean:
                continue

            # Split segment into elements
            parts = seg_text_clean.split(elem_sep)
            if not parts or not parts[0]:
                continue

            seg_id = parts[0].strip()
            elements = [p for p in parts[1:]]

            segments.append(RawSegment(
                segment_id=seg_id,
                elements=elements,
                line_number=seg_line,
                raw_text=seg_text_clean
            ))

        return segments

    def _find_payload_segment_end(self, raw: str, start_pos: int, seg_term: str, elem_sep: str) -> int:
        """Find the true segment terminator for embedded payload segments."""
        # Check if closing XML tag is present
        xml_close = "</ClinicalDocument>"
        xml_idx = raw.find(xml_close, start_pos)
        if xml_idx != -1:
            # Find next segment terminator after </ClinicalDocument>
            post_idx = raw.find(seg_term, xml_idx + len(xml_close))
            if post_idx != -1:
                return post_idx

        # Otherwise find standard segment terminator
        next_term = raw.find(seg_term, start_pos)
        if next_term != -1:
            return next_term
        return len(raw)
