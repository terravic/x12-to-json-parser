"""
C-CDA (Consolidated Clinical Document Architecture) XML Parser.

Extracts patient demographics, clinical document metadata, allergies,
medications, problems, vital signs, encounter summaries, and clinical notes
from standard HL7 C-CDA R2.1 / R1.1 XML documents.
"""

import base64
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Union


def _clean_tag(elem: ET.Element) -> str:
    """Return tag name without XML namespace."""
    if elem is None or elem.tag is None:
        return ""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _get_element_text(elem: Optional[ET.Element]) -> str:
    """Recursively extract text from element and all children."""
    if elem is None:
        return ""
    return "".join(elem.itertext()).strip()


class CCDAParser:
    """Parses C-CDA XML payloads into structured clinical JSON objects."""

    def __init__(self, xml_content: Union[str, bytes]):
        self.raw_content = self._prepare_content(xml_content)
        self.root: Optional[ET.Element] = None
        self._parse_xml()

    def _prepare_content(self, content: Union[str, bytes]) -> str:
        """Decode base64 or clean raw XML string."""
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        content = content.strip()

        # Check if content is Base64 encoded
        if not content.startswith("<"):
            try:
                decoded = base64.b64decode(content).decode("utf-8", errors="replace")
                if "<" in decoded and ">" in decoded:
                    return decoded.strip()
            except Exception:
                pass

        return content

    def _parse_xml(self) -> None:
        """Parse XML string into ElementTree."""
        try:
            clean_xml = self.raw_content
            xml_start = clean_xml.find("<?xml")
            if xml_start == -1:
                xml_start = clean_xml.find("<ClinicalDocument")
            if xml_start != -1:
                clean_xml = clean_xml[xml_start:]

            self.root = ET.fromstring(clean_xml)
        except Exception as e:
            raise ValueError(f"Failed to parse C-CDA XML: {e}")

    def _find_child_by_tag(self, parent: Optional[ET.Element], tag_name: str) -> Optional[ET.Element]:
        """Find immediate child matching local tag name."""
        if parent is None:
            return None
        for child in parent:
            if _clean_tag(child) == tag_name:
                return child
        return None

    def _find_descendant_by_tag(self, parent: Optional[ET.Element], tag_name: str) -> Optional[ET.Element]:
        """Find first descendant matching local tag name."""
        if parent is None:
            return None
        for elem in parent.iter():
            if _clean_tag(elem) == tag_name:
                return elem
        return None

    def _find_all_descendants_by_tag(self, parent: Optional[ET.Element], tag_name: str) -> List[ET.Element]:
        """Find all descendants matching local tag name."""
        if parent is None:
            return []
        return [elem for elem in parent.iter() if _clean_tag(elem) == tag_name]

    def parse(self) -> Dict[str, Any]:
        """Main entry point to parse C-CDA document into structured clinical JSON."""
        if self.root is None:
            return {}

        return {
            "document_metadata": self._parse_metadata(),
            "patient_demographics": self._parse_patient_demographics(),
            "allergies": self._parse_allergies(),
            "medications": self._parse_medications(),
            "problems_and_diagnoses": self._parse_problems(),
            "vital_signs": self._parse_vital_signs(),
            "encounters": self._parse_encounters(),
            "clinical_notes_and_evaluations": self._parse_clinical_notes(),
        }

    def _parse_metadata(self) -> Dict[str, Any]:
        """Extract document header metadata."""
        root = self.root
        if root is None:
            return {}

        title_elem = self._find_child_by_tag(root, "title")
        title = _get_element_text(title_elem) if title_elem is not None else "Clinical Document"

        effective_time = self._find_child_by_tag(root, "effectiveTime")
        doc_date = effective_time.attrib.get("value", "") if effective_time is not None else ""

        doc_id_elem = self._find_child_by_tag(root, "id")
        doc_id = {
            "root": doc_id_elem.attrib.get("root", "") if doc_id_elem is not None else "",
            "extension": doc_id_elem.attrib.get("extension", "") if doc_id_elem is not None else "",
        }

        confidentiality = self._find_child_by_tag(root, "confidentialityCode")
        conf_code = confidentiality.attrib.get("code", "N") if confidentiality is not None else "N"

        lang_elem = self._find_child_by_tag(root, "languageCode")
        lang_code = lang_elem.attrib.get("code", "en-US") if lang_elem is not None else "en-US"

        # Author / Clinician
        author_info: Dict[str, Any] = {}
        author_elem = self._find_child_by_tag(root, "author")
        if author_elem is not None:
            assigned_author = self._find_child_by_tag(author_elem, "assignedAuthor")
            if assigned_author is not None:
                assigned_person = self._find_child_by_tag(assigned_author, "assignedPerson")
                if assigned_person is not None:
                    name_elem = self._find_child_by_tag(assigned_person, "name")
                    if name_elem is not None:
                        author_info["name"] = self._parse_name_element(name_elem)
                org_elem = self._find_child_by_tag(assigned_author, "representedOrganization")
                if org_elem is not None:
                    org_name_elem = self._find_child_by_tag(org_elem, "name")
                    author_info["organization"] = _get_element_text(org_name_elem)

        # Custodian
        custodian_info: Dict[str, Any] = {}
        custodian_elem = self._find_child_by_tag(root, "custodian")
        if custodian_elem is not None:
            assigned_cust = self._find_descendant_by_tag(custodian_elem, "representedCustodianOrganization")
            if assigned_cust is not None:
                org_name = self._find_child_by_tag(assigned_cust, "name")
                custodian_info["organization_name"] = _get_element_text(org_name)
                addr_elem = self._find_child_by_tag(assigned_cust, "addr")
                if addr_elem is not None:
                    custodian_info["address"] = self._parse_address_element(addr_elem)

        return {
            "title": title,
            "document_id": doc_id,
            "effective_date": doc_date,
            "confidentiality_code": conf_code,
            "language_code": lang_code,
            "author": author_info,
            "custodian": custodian_info,
        }

    def _parse_patient_demographics(self) -> Dict[str, Any]:
        """Extract patient demographics from recordTarget."""
        root = self.root
        if root is None:
            return {}

        rec_target = self._find_child_by_tag(root, "recordTarget")
        if rec_target is None:
            return {}

        patient_role = self._find_child_by_tag(rec_target, "patientRole")
        if patient_role is None:
            return {}

        # Patient ID / MRN
        id_elem = self._find_child_by_tag(patient_role, "id")
        patient_id = id_elem.attrib.get("extension", "") if id_elem is not None else ""
        id_root = id_elem.attrib.get("root", "") if id_elem is not None else ""

        # Address
        addr_elem = self._find_child_by_tag(patient_role, "addr")
        address = self._parse_address_element(addr_elem) if addr_elem is not None else {}

        # Telecom / Phone
        telecom_elem = self._find_child_by_tag(patient_role, "telecom")
        telecom = telecom_elem.attrib.get("value", "") if telecom_elem is not None else ""

        # Patient details
        patient_elem = self._find_child_by_tag(patient_role, "patient")
        name_info: Dict[str, str] = {}
        dob = ""
        gender = ""
        marital_status = ""
        race = ""
        ethnic_group = ""

        if patient_elem is not None:
            name_elem = self._find_child_by_tag(patient_elem, "name")
            if name_elem is not None:
                name_info = self._parse_name_element(name_elem)

            birth_time = self._find_child_by_tag(patient_elem, "birthTime")
            if birth_time is not None:
                dob = birth_time.attrib.get("value", "")

            gender_elem = self._find_child_by_tag(patient_elem, "administrativeGenderCode")
            if gender_elem is not None:
                gender = gender_elem.attrib.get("displayName") or gender_elem.attrib.get("code", "")

            marital_elem = self._find_child_by_tag(patient_elem, "maritalStatusCode")
            if marital_elem is not None:
                marital_status = marital_elem.attrib.get("displayName") or marital_elem.attrib.get("code", "")

            race_elem = self._find_child_by_tag(patient_elem, "raceCode")
            if race_elem is not None:
                race = race_elem.attrib.get("displayName") or race_elem.attrib.get("code", "")

            ethnic_elem = self._find_child_by_tag(patient_elem, "ethnicGroupCode")
            if ethnic_elem is not None:
                ethnic_group = ethnic_elem.attrib.get("displayName") or ethnic_elem.attrib.get("code", "")

        return {
            "patient_identifier": patient_id,
            "patient_identifier_root": id_root,
            "name": name_info,
            "date_of_birth": dob,
            "gender": gender,
            "marital_status": marital_status,
            "race": race,
            "ethnic_group": ethnic_group,
            "address": address,
            "telecom": telecom,
        }

    def _parse_name_element(self, name_elem: ET.Element) -> Dict[str, str]:
        """Extract structured name components from <name> tag."""
        given_names = [_get_element_text(child) for child in name_elem if _clean_tag(child) == "given"]
        family_elem = self._find_child_by_tag(name_elem, "family")
        family = _get_element_text(family_elem) if family_elem is not None else ""
        prefix_elem = self._find_child_by_tag(name_elem, "prefix")
        prefix = _get_element_text(prefix_elem) if prefix_elem is not None else ""
        suffix_elem = self._find_child_by_tag(name_elem, "suffix")
        suffix = _get_element_text(suffix_elem) if suffix_elem is not None else ""

        first_name = given_names[0] if given_names else ""
        middle_name = " ".join(given_names[1:]) if len(given_names) > 1 else ""
        full_name = f"{prefix} {first_name} {middle_name} {family} {suffix}".strip()
        full_name = re.sub(r"\s+", " ", full_name)

        return {
            "full_name": full_name,
            "first_name": first_name,
            "middle_name": middle_name,
            "family_name": family,
            "prefix": prefix,
            "suffix": suffix,
        }

    def _parse_address_element(self, addr_elem: ET.Element) -> Dict[str, str]:
        """Extract address lines, city, state, postal code."""
        street_lines = [_get_element_text(child) for child in addr_elem if _clean_tag(child) == "streetAddressLine"]
        city_elem = self._find_child_by_tag(addr_elem, "city")
        city = _get_element_text(city_elem) if city_elem is not None else ""
        state_elem = self._find_child_by_tag(addr_elem, "state")
        state = _get_element_text(state_elem) if state_elem is not None else ""
        postal_elem = self._find_child_by_tag(addr_elem, "postalCode")
        postal_code = _get_element_text(postal_elem) if postal_elem is not None else ""
        country_elem = self._find_child_by_tag(addr_elem, "country")
        country = _get_element_text(country_elem) if country_elem is not None else "USA"

        return {
            "street_address": ", ".join(street_lines) if street_lines else "",
            "city": city,
            "state": state,
            "postal_code": postal_code,
            "country": country,
        }

    def _get_section_by_loinc(self, loinc_code: str) -> Optional[ET.Element]:
        """Locate section element matching a specific LOINC code."""
        root = self.root
        if root is None:
            return None

        sections = self._find_all_descendants_by_tag(root, "section")
        for sec in sections:
            code_elem = self._find_child_by_tag(sec, "code")
            if code_elem is not None and code_elem.attrib.get("code") == loinc_code:
                return sec
        return None

    def _parse_allergies(self) -> List[Dict[str, Any]]:
        """Parse Allergies and Adverse Reactions section (LOINC 48765-2)."""
        allergies: List[Dict[str, Any]] = []
        sec = self._get_section_by_loinc("48765-2")
        if sec is None:
            return allergies

        entries = [e for e in sec if _clean_tag(e) == "entry"]
        for entry in entries:
            # Check act status (concern act)
            act_status = "active"
            for act in entry.iter():
                if _clean_tag(act) == "act":
                    st = self._find_child_by_tag(act, "statusCode")
                    if st is not None:
                        act_status = st.attrib.get("code", "active")

            for obs in entry.iter():
                if _clean_tag(obs) == "observation":
                    substance_name = ""
                    substance_code = ""
                    code_system = ""
                    reaction = ""
                    severity = ""
                    status = act_status

                    # Check participant playingEntity
                    for pe in obs.iter():
                        if _clean_tag(pe) == "playingEntity":
                            code_elem = self._find_child_by_tag(pe, "code")
                            if code_elem is not None:
                                substance_name = code_elem.attrib.get("displayName", "")
                                substance_code = code_elem.attrib.get("code", "")
                                code_system = code_elem.attrib.get("codeSystemName", "RxNorm")

                    # Check reaction & severity
                    for er in obs.iter():
                        if _clean_tag(er) == "entryRelationship":
                            for inner_obs in er.iter():
                                if _clean_tag(inner_obs) == "observation":
                                    val_elem = self._find_child_by_tag(inner_obs, "value")
                                    if val_elem is not None:
                                        disp = val_elem.attrib.get("displayName", "")
                                        if disp in ("Mild", "Moderate", "Severe"):
                                            severity = disp
                                        elif disp:
                                            reaction = disp

                    if substance_name or reaction:
                        allergies.append({
                            "substance": substance_name or "Allergen",
                            "code": substance_code,
                            "code_system": code_system,
                            "status": status,
                            "reaction": reaction,
                            "severity": severity,
                        })

        if not allergies and sec is not None:
            text_elem = self._find_child_by_tag(sec, "text")
            if text_elem is not None:
                allergies.append({"narrative_summary": _get_element_text(text_elem)})

        return allergies

    def _parse_medications(self) -> List[Dict[str, Any]]:
        """Parse Medications section (LOINC 10160-0)."""
        medications: List[Dict[str, Any]] = []
        sec = self._get_section_by_loinc("10160-0")
        if sec is None:
            return medications

        entries = [e for e in sec if _clean_tag(e) == "entry"]
        for entry in entries:
            for sub_adm in entry.iter():
                if _clean_tag(sub_adm) == "substanceAdministration":
                    status_elem = self._find_child_by_tag(sub_adm, "statusCode")
                    status = status_elem.attrib.get("code", "active") if status_elem is not None else "active"

                    med_name = ""
                    rxnorm_code = ""
                    for mat in sub_adm.iter():
                        if _clean_tag(mat) == "manufacturedMaterial":
                            code_elem = self._find_child_by_tag(mat, "code")
                            if code_elem is not None:
                                med_name = code_elem.attrib.get("displayName", "")
                                rxnorm_code = code_elem.attrib.get("code", "")

                    dose_elem = self._find_child_by_tag(sub_adm, "doseQuantity")
                    dose = ""
                    if dose_elem is not None:
                        d_val = dose_elem.attrib.get("value", "")
                        d_unit = dose_elem.attrib.get("unit", "")
                        dose = f"{d_val} {d_unit}".strip()

                    route_elem = self._find_child_by_tag(sub_adm, "routeCode")
                    route = route_elem.attrib.get("displayName", "") if route_elem is not None else ""

                    inst_elem = self._find_child_by_tag(sub_adm, "text")
                    instructions = _get_element_text(inst_elem) if inst_elem is not None else ""

                    start_date = ""
                    end_date = ""
                    eff_time = self._find_child_by_tag(sub_adm, "effectiveTime")
                    if eff_time is not None:
                        low = self._find_child_by_tag(eff_time, "low")
                        high = self._find_child_by_tag(eff_time, "high")
                        if low is not None: start_date = low.attrib.get("value", "")
                        if high is not None: end_date = high.attrib.get("value", "")

                    medications.append({
                        "medication_name": med_name or instructions or "Medication",
                        "rxnorm_code": rxnorm_code,
                        "dose": dose,
                        "route": route,
                        "instructions": instructions,
                        "status": status,
                        "start_date": start_date,
                        "end_date": end_date,
                    })

        if not medications and sec is not None:
            text_elem = self._find_child_by_tag(sec, "text")
            if text_elem is not None:
                medications.append({"narrative_summary": _get_element_text(text_elem)})

        return medications

    def _parse_problems(self) -> List[Dict[str, Any]]:
        """Parse Problems and Diagnoses section (LOINC 11450-4)."""
        problems: List[Dict[str, Any]] = []
        sec = self._get_section_by_loinc("11450-4")
        if sec is None:
            return problems

        entries = [e for e in sec if _clean_tag(e) == "entry"]
        for entry in entries:
            for obs in entry.iter():
                if _clean_tag(obs) == "observation":
                    val_elem = self._find_child_by_tag(obs, "value")
                    if val_elem is not None and val_elem.attrib.get("code"):
                        prob_name = val_elem.attrib.get("displayName", "")
                        prob_code = val_elem.attrib.get("code", "")
                        code_sys = val_elem.attrib.get("codeSystemName", "ICD-10-CM")

                        onset_date = ""
                        eff_time = self._find_child_by_tag(obs, "effectiveTime")
                        if eff_time is not None:
                            low = self._find_child_by_tag(eff_time, "low")
                            onset_date = low.attrib.get("value", "") if low is not None else eff_time.attrib.get("value", "")

                        status = "Active"
                        for er in obs.iter():
                            if _clean_tag(er) == "value" and er.attrib.get("displayName") in ("Active", "Resolved", "Inactive"):
                                status = er.attrib.get("displayName")

                        problems.append({
                            "problem_name": prob_name or "Condition",
                            "code": prob_code,
                            "code_system": code_sys,
                            "status": status,
                            "onset_date": onset_date,
                        })

        if not problems and sec is not None:
            text_elem = self._find_child_by_tag(sec, "text")
            if text_elem is not None:
                problems.append({"narrative_summary": _get_element_text(text_elem)})

        return problems

    def _parse_vital_signs(self) -> List[Dict[str, Any]]:
        """Parse Vital Signs section (LOINC 8716-3)."""
        vitals: List[Dict[str, Any]] = []
        sec = self._get_section_by_loinc("8716-3")
        if sec is None:
            return vitals

        entries = [e for e in sec if _clean_tag(e) == "entry"]
        for entry in entries:
            for obs in entry.iter():
                if _clean_tag(obs) == "observation":
                    code_elem = self._find_child_by_tag(obs, "code")
                    val_elem = self._find_child_by_tag(obs, "value")
                    time_elem = self._find_child_by_tag(obs, "effectiveTime")

                    if code_elem is not None and val_elem is not None:
                        test_name = code_elem.attrib.get("displayName", "")
                        loinc_code = code_elem.attrib.get("code", "")
                        val = val_elem.attrib.get("value", "")
                        unit = val_elem.attrib.get("unit", "")
                        rec_date = time_elem.attrib.get("value", "") if time_elem is not None else ""

                        if test_name or val:
                            vitals.append({
                                "measurement_name": test_name or "Vital Sign",
                                "loinc_code": loinc_code,
                                "value": val,
                                "unit": unit,
                                "recorded_date": rec_date,
                            })

        if not vitals and sec is not None:
            text_elem = self._find_child_by_tag(sec, "text")
            if text_elem is not None:
                vitals.append({"narrative_summary": _get_element_text(text_elem)})

        return vitals

    def _parse_encounters(self) -> List[Dict[str, Any]]:
        """Parse Encounters section (LOINC 46240-8)."""
        encounters: List[Dict[str, Any]] = []
        sec = self._get_section_by_loinc("46240-8")
        if sec is None:
            return encounters

        entries = [e for e in sec if _clean_tag(e) == "entry"]
        for entry in entries:
            for enc in entry.iter():
                if _clean_tag(enc) == "encounter":
                    code_elem = self._find_child_by_tag(enc, "code")
                    enc_type = code_elem.attrib.get("displayName", "") if code_elem is not None else "Encounter"
                    code = code_elem.attrib.get("code", "") if code_elem is not None else ""

                    eff_time = self._find_child_by_tag(enc, "effectiveTime")
                    enc_date = eff_time.attrib.get("value", "") if eff_time is not None else ""

                    provider_name = ""
                    for person in enc.iter():
                        if _clean_tag(person) == "assignedPerson":
                            name_elem = self._find_child_by_tag(person, "name")
                            if name_elem is not None:
                                provider_name = self._parse_name_element(name_elem)["full_name"]

                    encounters.append({
                        "encounter_type": enc_type,
                        "cpt_or_snomed_code": code,
                        "date": enc_date,
                        "attending_provider": provider_name,
                    })

        if not encounters and sec is not None:
            text_elem = self._find_child_by_tag(sec, "text")
            if text_elem is not None:
                encounters.append({"narrative_summary": _get_element_text(text_elem)})

        return encounters

    def _parse_clinical_notes(self) -> Dict[str, Any]:
        """Extract Chief Complaint, Assessment & Plan, Progress Notes, and Medical Necessity justification."""
        notes: Dict[str, Any] = {}

        # Chief Complaint / Reason for Visit (LOINC 29299-5 or 10154-3)
        cc_sec = self._get_section_by_loinc("29299-5")
        if cc_sec is None:
            cc_sec = self._get_section_by_loinc("10154-3")
        if cc_sec is not None:
            text_elem = self._find_child_by_tag(cc_sec, "text")
            if text_elem is not None:
                notes["chief_complaint_and_reason_for_visit"] = _get_element_text(text_elem)

        # Assessment and Plan (LOINC 51847-2)
        ap_sec = self._get_section_by_loinc("51847-2")
        if ap_sec is not None:
            text_elem = self._find_child_by_tag(ap_sec, "text")
            if text_elem is not None:
                notes["assessment_and_plan"] = _get_element_text(text_elem)

        # Progress Note / Medical Necessity Evaluation (LOINC 11506-3 or 28570-0)
        pn_sec = self._get_section_by_loinc("11506-3")
        if pn_sec is None:
            pn_sec = self._get_section_by_loinc("28570-0")
        if pn_sec is not None:
            text_elem = self._find_child_by_tag(pn_sec, "text")
            if text_elem is not None:
                notes["progress_note_medical_necessity_evaluation"] = _get_element_text(text_elem)

        return notes
