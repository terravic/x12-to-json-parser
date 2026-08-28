# EDI X12 (5010) to JSON Semantic Mapping Specifications

This document defines the field-by-field and loop-by-loop mapping rules implemented by the X12 Healthcare Parser and rendered within the Visual Dashboard.

---

## 1. Control & Envelope Hierarchy

| Segment | Position / Element | Semantic JSON Path | Loop / Context | Business Meaning |
|:---|:---|:---|:---|:---|
| **ISA** | ISA06 / ISA08 | `interchange_control_header.interchange_sender_id` / `interchange_receiver_id` | Envelope | Trading partner routing IDs (clearinghouse, payer, provider) |
| **ISA** | ISA09 / ISA10 | `interchange_control_header.interchange_date` / `interchange_time` | Envelope | Timestamp of interchange generation |
| **ISA** | ISA13 | `interchange_control_header.interchange_control_number` | Envelope | Unique 9-digit tracking identifier matched with IEA |
| **GS** | GS01 / GS08 | `functional_groups[].functional_identifier_code` / `version` | Group | Identifies transaction family (`HC`=837, `HP`=835, `HR`=277, `HS`=270, `HB`=271, `HI`=278) |
| **GS** | GS06 | `functional_groups[].group_control_number` | Group | Unique group sequence tracking number matched with GE |
| **ST** | ST01 / ST02 | `transaction_sets[].transaction_type` / `transaction_set_control_number` | Set Header | Transaction identifier (`837`, `835`, `270`, `271`, `277`, `275`, `278`) |
| **SE** | SE01 / SE02 | `transaction_sets[].transaction_trailer.number_of_included_segments` | Set Trailer | Integrity check comparing segment count and control number |

---

## 2. Business Entity & Participant Loops (Loop 2000 / 2010)

| Segment | Code Qualifier | Semantic JSON Path | Entity Role |
|:---|:---|:---|:---|
| **NM1** | `NM101 = '85'` | `parsed_transaction.billing_provider` | Billing Provider (Hospital, Clinic, Group) |
| **NM1** | `NM101 = '82'` | `parsed_transaction.rendering_provider` | Rendering / Attending Physician |
| **NM1** | `NM101 = 'PR'` | `parsed_transaction.payer` | Payer / Health Plan |
| **NM1** | `NM101 = 'IL'` | `parsed_transaction.subscriber` | Insured Subscriber / Policy Holder |
| **NM1** | `NM101 = 'QC'` | `parsed_transaction.patient` | Patient (if dependent / distinct from subscriber) |
| **NM1** | `NM101 = '41'` | `parsed_transaction.submitter` | Submitter / Clearinghouse |
| **NM1** | `NM101 = '40'` | `parsed_transaction.receiver` | Receiver / Processor |
| **N3 / N4**| - | `*.address.address_line_1`, `*.geographic_location.city`, `state`, `postal_code` | Street address, city, state, and 9-digit ZIP |
| **DMG** | `DMG01 = 'D8'` | `*.demographics.date_of_birth`, `*.demographics.gender` | Date of birth (`YYYYMMDD`) and gender code (`M`/`F`/`U`) |

---

## 3. 837 Health Care Claim (Professional 837P & Institutional 837I)

| Segment | Position | Semantic JSON Path | Business Description |
|:---|:---|:---|:---|
| **CLM** | CLM01 | `claims[].claim_id` | Patient account or unique claim submitter identifier |
| **CLM** | CLM02 | `claims[].total_claim_charge_amount` | Total billed dollar amount for claim |
| **CLM** | CLM05-1 | `claims[].facility_code` | Place of Service / Facility Type Code (e.g. `11`=Office, `21`=Inpatient) |
| **DTP** | DTP01 = `472` | `claims[].dates.service_date` | Date of service or service date range (`YYYYMMDD` or `YYYYMMDD-YYYYMMDD`) |
| **HI** | HI01-1 = `ABK` | `claims[].diagnoses[].code` | Principal ICD-10-CM diagnosis code (e.g., `I10`, `E11.9`) |
| **HI** | HI02-1 = `ABF` | `claims[].diagnoses[].code` | Secondary / Other ICD-10-CM diagnosis code |
| **LX** | LX01 | `claims[].service_lines[].line_number` | Sequential line counter (1, 2, 3...) |
| **SV1** | SV101-2 | `claims[].service_lines[].procedure.procedure_code` | CPT or HCPCS procedure code (e.g., `99214`, `80053`) |
| **SV1** | SV102 | `claims[].service_lines[].charge_amount` | Billed line item dollar amount |
| **SV1** | SV103 | `claims[].service_lines[].unit_count` | Number of service units / quantity billed |

---

## 4. 835 Electronic Remittance Advice (ERA) & Payment Adjudication

| Segment | Position | Semantic JSON Path | Business Description |
|:---|:---|:---|:---|
| **BPR** | BPR02 | `financial_information.total_payment_amount` | Total electronic EFT / check payment amount |
| **BPR** | BPR04 | `financial_information.payment_method` | Payment method (`ACH`=Direct Deposit, `CHK`=Check) |
| **TRN** | TRN02 | `reassociation_trace.check_or_eft_trace_number` | Trace identifier for bank reconciliation |
| **CLP** | CLP01 | `claims[].patient_control_number` | Provider's patient account number |
| **CLP** | CLP02 | `claims[].claim_status_code` | Claim adjudication status (`1`=Processed Primary, `2`=Secondary, `4`=Denied) |
| **CLP** | CLP03 | `claims[].total_claim_charge_amount` | Total billed amount submitted by provider |
| **CLP** | CLP04 | `claims[].claim_payment_amount` | Net dollar amount paid by payer |
| **CLP** | CLP05 | `claims[].patient_responsibility_amount` | Patient deductible, coinsurance, or copay |
| **CAS** | CAS01 | `claims[].adjustments[].group_code` | Claim Adjustment Group (`CO`=Contractual Obligation, `PR`=Patient Responsibility) |
| **CAS** | CAS02 | `claims[].adjustments[].reason_code` | CARC adjustment reason code (e.g., `45`=Charge exceeds fee schedule) |
| **CAS** | CAS03 | `claims[].adjustments[].adjustment_amount` | Dollar amount subtracted from submitted charge |

---

## 5. 277 Claim Status Request & Attachment Flagging

| Segment | Position | Semantic JSON Path | Business Description |
|:---|:---|:---|:---|
| **STC** | STC01-1 | `required_attachments[].status_category_code` | Claim status category (`R0`-`R5` indicates clinical attachment request) |
| **STC** | STC01-2 | `required_attachments[].status_code` | Detailed status code (e.g., `21`=Missing documentation) |
| **PWK** | PWK01 | `required_attachments[].attachment_report_type_code` | LOINC / X12 attachment code (e.g., `03`=Report, `04`=Operative note) |
| **PWK** | PWK02 | `required_attachments[].attachment_transmission_code` | Transmission method (`EL`=Electronic, `FX`=Fax, `BM`=By Mail) |

---

## 6. 275 & C-CDA XML Clinical Integration

| Segment / XML Node | Semantic JSON Path | Clinical Content |
|:---|:---|:---|
| **BDS03 / BIN02** | `attached_clinical_data` | Extracts and parses HL7 C-CDA R2.1 XML envelope |
| `<patient>` | `attached_clinical_data.patient_demographics` | Name, DOB, Gender, Address, Telecom |
| `<substanceAdministration>` | `attached_clinical_data.medications[]` | Active medication name, RxNorm code, dose, route |
| `<observation classCode="OBS">`| `attached_clinical_data.allergies[]` | Allergen substance name, reaction, severity |
| `<observation classCode="COND">`| `attached_clinical_data.problems_and_diagnoses[]`| ICD-10-CM / SNOMED CT problem description & status |
| `<organizer classCode="CLUSTER">`| `attached_clinical_data.vital_signs[]` | Systolic/Diastolic BP, Heart Rate, SpO2, BMI |
| `<component><section>` | `attached_clinical_data.clinical_notes_and_evaluations` | Progress note narrative & medical necessity justification |
