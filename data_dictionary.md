# Phase 1 Data Dictionary

## Purpose and scope

This document describes the source database schema for the ten datasets included in the Phase 1 Data Safe Haven POC.

- Database schema: `haven_poc_source`
- Metadata source: `INFORMATION_SCHEMA`
- Datasets documented: 10
- Column entries documented: 302
- Clinical rows read during schema inventory: `False`
- Source data modified during schema inventory: `False`

This is a schema-level reference generated from the dataset catalogue and MySQL INFORMATION_SCHEMA metadata. It does not contain clinical row values.

Column descriptions, clinical meanings, accepted values and business rules are not inferred. They require confirmation from the appropriate data owner or approved documentation.

## Dataset summary

| Dataset ID | Display label | Original worksheet | Source table | Columns |
|---|---|---|---|---:|
| `DS_PATIENT` | Patient Demographics | `bi_patient data` | `bi_patient_data` | 25 |
| `DS_VISIT` | Visits | `bi_visit data` | `bi_visit_data` | 24 |
| `DS_DIAGNOSIS` | Diagnoses | `bi_diagnosis data` | `bi_diagnosis_data` | 17 |
| `DS_ENDOSCOPY_PROCEDURE` | Endoscopy Procedures | `bi_endoscopy_procedure d` | `stg_ds_endoscopy_procedure` | 36 |
| `DS_MEDICATION` | Medications | `bi_medication data` | `stg_ds_medication` | 36 |
| `DS_NEUROLOGY_PROCEDURE` | Neurology Procedures | `bi_neurology_procedure d` | `stg_ds_neurology_procedure` | 37 |
| `DS_OPERATION_PROCEDURE` | Operation Procedures | `bi_operation_procedure sample d` | `stg_ds_operation_procedure` | 56 |
| `DS_RADIOLOGY_PROCEDURE` | Radiology Procedures | `bi_radiology_procedure d` | `stg_ds_radiology_procedure` | 39 |
| `DS_LABORATORY_PROCEDURE` | Laboratory Procedures | `bi_laboratory_procedure ` | `stg_ds_laboratory_procedure` | 21 |
| `DS_VITAL_SIGNS` | Vital Signs | `vitalsign data` | `stg_ds_vital_signs` | 11 |

## Patient Demographics (`DS_PATIENT`)

- Original worksheet: `bi_patient data`
- Source table: `bi_patient_data`
- Database schema: `haven_poc_source`
- Number of columns: 25

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `bigint` | NO | YES | NO | Not recorded |
| 2 | `Age` | `bigint` | YES | NO | NO | Not recorded |
| 3 | `DOB` | `datetime` | YES | NO | NO | Not recorded |
| 4 | `Gender` | `text` | YES | NO | NO | Not recorded |
| 5 | `Marital_status` | `text` | YES | NO | NO | Not recorded |
| 6 | `Warganegara` | `text` | YES | NO | NO | Not recorded |
| 7 | `Posscode` | `bigint` | YES | NO | NO | Not recorded |
| 8 | `State` | `text` | YES | NO | NO | Not recorded |
| 9 | `District` | `text` | YES | NO | NO | Not recorded |
| 10 | `Status` | `text` | YES | NO | NO | Not recorded |
| 11 | `Survival_status` | `text` | YES | NO | NO | Not recorded |
| 12 | `Dateofdeath` | `datetime` | YES | NO | NO | Not recorded |
| 13 | `Type` | `text` | YES | NO | NO | Not recorded |
| 14 | `Occupation` | `text` | YES | NO | NO | Not recorded |
| 15 | `Race` | `bigint` | YES | NO | NO | Not recorded |
| 16 | `Spoken_language` | `text` | YES | NO | NO | Not recorded |
| 17 | `OKU_status` | `text` | YES | NO | NO | Not recorded |
| 18 | `visit_2019` | `text` | YES | NO | NO | Not recorded |
| 19 | `QC_gender` | `double` | YES | NO | NO | Not recorded |
| 20 | `QC_visit` | `text` | YES | NO | NO | Not recorded |
| 21 | `visit_2020` | `text` | YES | NO | NO | Not recorded |
| 22 | `visit_2021` | `text` | YES | NO | NO | Not recorded |
| 23 | `QC` | `double` | YES | NO | NO | Not recorded |
| 24 | `QC_Age` | `text` | YES | NO | NO | Not recorded |
| 25 | `QC_bloodprofile` | `text` | YES | NO | NO | Not recorded |

## Visits (`DS_VISIT`)

- Original worksheet: `bi_visit data`
- Source table: `bi_visit_data`
- Database schema: `haven_poc_source`
- Number of columns: 24

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `bigint` | YES | NO | YES | haven_poc_source.bi_patient_data.DeID |
| 2 | `VisitID` | `bigint` | NO | YES | NO | Not recorded |
| 3 | `Visit_type` | `text` | YES | NO | NO | Not recorded |
| 4 | `Patient_type` | `text` | YES | NO | NO | Not recorded |
| 5 | `Registration_datetime` | `datetime` | YES | NO | NO | Not recorded |
| 6 | `Admission_datetime` | `datetime` | YES | NO | NO | Not recorded |
| 7 | `Seen_time` | `datetime` | YES | NO | NO | Not recorded |
| 8 | `Triage_level` | `double` | YES | NO | NO | Not recorded |
| 9 | `location_code` | `text` | YES | NO | NO | Not recorded |
| 10 | `Location_id` | `double` | YES | NO | NO | Not recorded |
| 11 | `Location_description` | `text` | YES | NO | NO | Not recorded |
| 12 | `Specialty` | `text` | YES | NO | NO | Not recorded |
| 13 | `Sub_specialty` | `text` | YES | NO | NO | Not recorded |
| 14 | `Discharge_datetime` | `datetime` | YES | NO | NO | Not recorded |
| 15 | `Discharge_type` | `text` | YES | NO | NO | Not recorded |
| 16 | `Length_of_stay` | `double` | YES | NO | NO | Not recorded |
| 17 | `Waiting_time` | `text` | YES | NO | NO | Not recorded |
| 18 | `QC` | `double` | YES | NO | NO | Not recorded |
| 19 | `casemix` | `text` | YES | NO | NO | Not recorded |
| 20 | `lab` | `double` | YES | NO | NO | Not recorded |
| 21 | `QC_locationcode` | `text` | YES | NO | NO | Not recorded |
| 22 | `qc_opvisit` | `text` | YES | NO | NO | Not recorded |
| 23 | `op_kehadiranpesakit` | `text` | YES | NO | NO | Not recorded |
| 24 | `chk_symptoms` | `text` | YES | NO | NO | Not recorded |

## Diagnoses (`DS_DIAGNOSIS`)

- Original worksheet: `bi_diagnosis data`
- Source table: `bi_diagnosis_data`
- Database schema: `haven_poc_source`
- Number of columns: 17

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `bigint` | YES | NO | YES | haven_poc_source.bi_patient_data.DeID; haven_poc_source.bi_visit_data.DeID |
| 2 | `VisitID` | `bigint` | YES | NO | YES | haven_poc_source.bi_visit_data.VisitID |
| 3 | `Diagnosis_datetime` | `datetime` | YES | NO | NO | Not recorded |
| 4 | `kod` | `text` | YES | NO | NO | Not recorded |
| 5 | `Description` | `text` | YES | NO | NO | Not recorded |
| 6 | `Diagnosis_level` | `text` | YES | NO | NO | Not recorded |
| 7 | `Diagnosis_Category` | `text` | YES | NO | NO | Not recorded |
| 8 | `Method_of_diagnosis` | `text` | YES | NO | NO | Not recorded |
| 9 | `Diagnosis_by` | `text` | YES | NO | NO | Not recorded |
| 10 | `Remarks` | `text` | YES | NO | NO | Not recorded |
| 11 | `Age_year_diagnosis` | `double` | YES | NO | NO | Not recorded |
| 12 | `Age_month_diagnosis` | `double` | YES | NO | NO | Not recorded |
| 13 | `diagnosisid` | `bigint` | NO | YES | NO | Not recorded |
| 14 | `DOB` | `datetime` | YES | NO | NO | Not recorded |
| 15 | `checklist` | `text` | YES | NO | NO | Not recorded |
| 16 | `QC_round1` | `double` | YES | NO | NO | Not recorded |
| 17 | `tbl` | `text` | YES | NO | NO | Not recorded |

## Endoscopy Procedures (`DS_ENDOSCOPY_PROCEDURE`)

- Original worksheet: `bi_endoscopy_procedure d`
- Source table: `stg_ds_endoscopy_procedure`
- Database schema: `haven_poc_source`
- Number of columns: 36

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `longtext` | YES | NO | NO | Not recorded |
| 2 | `VisitID` | `longtext` | YES | NO | NO | Not recorded |
| 3 | `Test_code` | `longtext` | YES | NO | NO | Not recorded |
| 4 | `Test_description` | `longtext` | YES | NO | NO | Not recorded |
| 5 | `Internal_code` | `longtext` | YES | NO | NO | Not recorded |
| 6 | `Procedure_type` | `longtext` | YES | NO | NO | Not recorded |
| 7 | `Procedure_duration` | `longtext` | YES | NO | NO | Not recorded |
| 8 | `Procedure_date` | `longtext` | YES | NO | NO | Not recorded |
| 9 | `Requester` | `longtext` | YES | NO | NO | Not recorded |
| 10 | `Requester_specialty` | `longtext` | YES | NO | NO | Not recorded |
| 11 | `MLT1` | `longtext` | YES | NO | NO | Not recorded |
| 12 | `MLT3` | `longtext` | YES | NO | NO | Not recorded |
| 13 | `MLT4` | `longtext` | YES | NO | NO | Not recorded |
| 14 | `MLT5` | `longtext` | YES | NO | NO | Not recorded |
| 15 | `gastroenterologist1` | `longtext` | YES | NO | NO | Not recorded |
| 16 | `gastroenterologist2` | `longtext` | YES | NO | NO | Not recorded |
| 17 | `gastroenterologist3` | `longtext` | YES | NO | NO | Not recorded |
| 18 | `gastroenterologist4` | `longtext` | YES | NO | NO | Not recorded |
| 19 | `gastroenterologist5` | `longtext` | YES | NO | NO | Not recorded |
| 20 | `Order_urgency` | `longtext` | YES | NO | NO | Not recorded |
| 21 | `Assisting_aids` | `longtext` | YES | NO | NO | Not recorded |
| 22 | `Accession_number` | `longtext` | YES | NO | NO | Not recorded |
| 23 | `Result_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 24 | `Final_report` | `longtext` | YES | NO | NO | Not recorded |
| 25 | `Result_description` | `longtext` | YES | NO | NO | Not recorded |
| 26 | `Charges` | `longtext` | YES | NO | NO | Not recorded |
| 27 | `Endoscopy_section` | `longtext` | YES | NO | NO | Not recorded |
| 28 | `Modality` | `longtext` | YES | NO | NO | Not recorded |
| 29 | `DurationA` | `longtext` | YES | NO | NO | Not recorded |
| 30 | `DurationB` | `longtext` | YES | NO | NO | Not recorded |
| 31 | `DurationC` | `longtext` | YES | NO | NO | Not recorded |
| 32 | `DurationD` | `longtext` | YES | NO | NO | Not recorded |
| 33 | `DurationE` | `longtext` | YES | NO | NO | Not recorded |
| 34 | `DurationF` | `longtext` | YES | NO | NO | Not recorded |
| 35 | `DurationG` | `longtext` | YES | NO | NO | Not recorded |
| 36 | `idordered` | `longtext` | YES | NO | NO | Not recorded |

## Medications (`DS_MEDICATION`)

- Original worksheet: `bi_medication data`
- Source table: `stg_ds_medication`
- Database schema: `haven_poc_source`
- Number of columns: 36

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `longtext` | YES | NO | NO | Not recorded |
| 2 | `VisitID` | `longtext` | YES | NO | NO | Not recorded |
| 3 | `Patient_category` | `longtext` | YES | NO | NO | Not recorded |
| 4 | `Drug_code` | `longtext` | YES | NO | NO | Not recorded |
| 5 | `Drug_name` | `longtext` | YES | NO | NO | Not recorded |
| 6 | `Nursing1` | `longtext` | YES | NO | NO | Not recorded |
| 7 | `Nursing2` | `longtext` | YES | NO | NO | Not recorded |
| 8 | `Nursing3` | `longtext` | YES | NO | NO | Not recorded |
| 9 | `Nursing4` | `longtext` | YES | NO | NO | Not recorded |
| 10 | `Nursing5` | `longtext` | YES | NO | NO | Not recorded |
| 11 | `Pharmacy1` | `longtext` | YES | NO | NO | Not recorded |
| 12 | `Pharmacy2` | `longtext` | YES | NO | NO | Not recorded |
| 13 | `Pharmacy3` | `longtext` | YES | NO | NO | Not recorded |
| 14 | `Pharmacy4` | `longtext` | YES | NO | NO | Not recorded |
| 15 | `Pharmacy5` | `longtext` | YES | NO | NO | Not recorded |
| 16 | `Prescriber1` | `longtext` | YES | NO | NO | Not recorded |
| 17 | `Prescriber2` | `longtext` | YES | NO | NO | Not recorded |
| 18 | `Prescriber3` | `longtext` | YES | NO | NO | Not recorded |
| 19 | `Prescriber4` | `longtext` | YES | NO | NO | Not recorded |
| 20 | `Prescriber5` | `longtext` | YES | NO | NO | Not recorded |
| 21 | `Prescription_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 22 | `Screen_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 23 | `Dispense_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 24 | `Serving_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 25 | `Stop_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 26 | `DurationA` | `longtext` | YES | NO | NO | Not recorded |
| 27 | `DurationB` | `longtext` | YES | NO | NO | Not recorded |
| 28 | `DurationC` | `longtext` | YES | NO | NO | Not recorded |
| 29 | `DurationD` | `longtext` | YES | NO | NO | Not recorded |
| 30 | `Omission_reason` | `longtext` | YES | NO | NO | Not recorded |
| 31 | `Dose` | `longtext` | YES | NO | NO | Not recorded |
| 32 | `Duration` | `longtext` | YES | NO | NO | Not recorded |
| 33 | `Method` | `longtext` | YES | NO | NO | Not recorded |
| 34 | `Cost_per_unit` | `longtext` | YES | NO | NO | Not recorded |
| 35 | `Total_cost` | `longtext` | YES | NO | NO | Not recorded |
| 36 | `idpreskripsi` | `longtext` | YES | NO | NO | Not recorded |

## Neurology Procedures (`DS_NEUROLOGY_PROCEDURE`)

- Original worksheet: `bi_neurology_procedure d`
- Source table: `stg_ds_neurology_procedure`
- Database schema: `haven_poc_source`
- Number of columns: 37

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `longtext` | YES | NO | NO | Not recorded |
| 2 | `VisitID` | `longtext` | YES | NO | NO | Not recorded |
| 3 | `Test_code` | `longtext` | YES | NO | NO | Not recorded |
| 4 | `Test_description` | `longtext` | YES | NO | NO | Not recorded |
| 5 | `Internal_code` | `longtext` | YES | NO | NO | Not recorded |
| 6 | `Procedure_type` | `longtext` | YES | NO | NO | Not recorded |
| 7 | `Procedure_date` | `longtext` | YES | NO | NO | Not recorded |
| 8 | `Procedure_duration` | `longtext` | YES | NO | NO | Not recorded |
| 9 | `Requester` | `longtext` | YES | NO | NO | Not recorded |
| 10 | `Requester_specialty` | `longtext` | YES | NO | NO | Not recorded |
| 11 | `MLT1` | `longtext` | YES | NO | NO | Not recorded |
| 12 | `MLT2` | `longtext` | YES | NO | NO | Not recorded |
| 13 | `MLT3` | `longtext` | YES | NO | NO | Not recorded |
| 14 | `MLT4` | `longtext` | YES | NO | NO | Not recorded |
| 15 | `MLT5` | `longtext` | YES | NO | NO | Not recorded |
| 16 | `Neurologist1` | `longtext` | YES | NO | NO | Not recorded |
| 17 | `Neurologist2` | `longtext` | YES | NO | NO | Not recorded |
| 18 | `Neurologist3` | `longtext` | YES | NO | NO | Not recorded |
| 19 | `Neurologist4` | `longtext` | YES | NO | NO | Not recorded |
| 20 | `Neurologist5` | `longtext` | YES | NO | NO | Not recorded |
| 21 | `Order_urgency` | `longtext` | YES | NO | NO | Not recorded |
| 22 | `Assisting_aids` | `longtext` | YES | NO | NO | Not recorded |
| 23 | `Accession_number` | `longtext` | YES | NO | NO | Not recorded |
| 24 | `Result_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 25 | `Final_report` | `longtext` | YES | NO | NO | Not recorded |
| 26 | `Result_description` | `longtext` | YES | NO | NO | Not recorded |
| 27 | `Charges` | `longtext` | YES | NO | NO | Not recorded |
| 28 | `Neurology_section` | `longtext` | YES | NO | NO | Not recorded |
| 29 | `Modality` | `longtext` | YES | NO | NO | Not recorded |
| 30 | `DurationA` | `longtext` | YES | NO | NO | Not recorded |
| 31 | `DurationB` | `longtext` | YES | NO | NO | Not recorded |
| 32 | `DurationC` | `longtext` | YES | NO | NO | Not recorded |
| 33 | `DurationD` | `longtext` | YES | NO | NO | Not recorded |
| 34 | `DurationE` | `longtext` | YES | NO | NO | Not recorded |
| 35 | `DurationF` | `longtext` | YES | NO | NO | Not recorded |
| 36 | `DurationG` | `longtext` | YES | NO | NO | Not recorded |
| 37 | `idornneurology` | `longtext` | YES | NO | NO | Not recorded |

## Operation Procedures (`DS_OPERATION_PROCEDURE`)

- Original worksheet: `bi_operation_procedure sample d`
- Source table: `stg_ds_operation_procedure`
- Database schema: `haven_poc_source`
- Number of columns: 56

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `longtext` | YES | NO | NO | Not recorded |
| 2 | `VisitID` | `longtext` | YES | NO | NO | Not recorded |
| 3 | `Surgery_date` | `longtext` | YES | NO | NO | Not recorded |
| 4 | `OT_location` | `longtext` | YES | NO | NO | Not recorded |
| 5 | `Theater_room` | `longtext` | YES | NO | NO | Not recorded |
| 6 | `Booking_ID` | `longtext` | YES | NO | NO | Not recorded |
| 7 | `Operation_status` | `longtext` | YES | NO | NO | Not recorded |
| 8 | `Surgery_type` | `longtext` | YES | NO | NO | Not recorded |
| 9 | `Diagnosis_code1` | `longtext` | YES | NO | NO | Not recorded |
| 10 | `Diagnosis_code2` | `longtext` | YES | NO | NO | Not recorded |
| 11 | `Diagnosis_code3` | `longtext` | YES | NO | NO | Not recorded |
| 12 | `Diagnosis_code4` | `longtext` | YES | NO | NO | Not recorded |
| 13 | `Diagnosis_code5` | `longtext` | YES | NO | NO | Not recorded |
| 14 | `Procedure_code1` | `longtext` | YES | NO | NO | Not recorded |
| 15 | `Procedure_code2` | `longtext` | YES | NO | NO | Not recorded |
| 16 | `Procedure_code3` | `longtext` | YES | NO | NO | Not recorded |
| 17 | `Procedure_code4` | `longtext` | YES | NO | NO | Not recorded |
| 18 | `Procedure_code5` | `longtext` | YES | NO | NO | Not recorded |
| 19 | `Description1` | `longtext` | YES | NO | NO | Not recorded |
| 20 | `Description2` | `longtext` | YES | NO | NO | Not recorded |
| 21 | `Description3` | `longtext` | YES | NO | NO | Not recorded |
| 22 | `Description4` | `longtext` | YES | NO | NO | Not recorded |
| 23 | `Description5` | `longtext` | YES | NO | NO | Not recorded |
| 24 | `Internal_code1` | `longtext` | YES | NO | NO | Not recorded |
| 25 | `Internal_code2` | `longtext` | YES | NO | NO | Not recorded |
| 26 | `Internal_code3` | `longtext` | YES | NO | NO | Not recorded |
| 27 | `Internal_code4` | `longtext` | YES | NO | NO | Not recorded |
| 28 | `Internal_code5` | `longtext` | YES | NO | NO | Not recorded |
| 29 | `Surgeon1` | `longtext` | YES | NO | NO | Not recorded |
| 30 | `Surgeon2` | `longtext` | YES | NO | NO | Not recorded |
| 31 | `Surgeon3` | `longtext` | YES | NO | NO | Not recorded |
| 32 | `Surgeon4` | `longtext` | YES | NO | NO | Not recorded |
| 33 | `Surgeon5` | `longtext` | YES | NO | NO | Not recorded |
| 34 | `anaesthetist1` | `longtext` | YES | NO | NO | Not recorded |
| 35 | `anaesthetist2` | `longtext` | YES | NO | NO | Not recorded |
| 36 | `anaesthetist3` | `longtext` | YES | NO | NO | Not recorded |
| 37 | `anaesthetist4` | `longtext` | YES | NO | NO | Not recorded |
| 38 | `anaesthetist5` | `longtext` | YES | NO | NO | Not recorded |
| 39 | `Nurse1` | `longtext` | YES | NO | NO | Not recorded |
| 40 | `Nurse2` | `longtext` | YES | NO | NO | Not recorded |
| 41 | `Nurse3` | `longtext` | YES | NO | NO | Not recorded |
| 42 | `Nurse4` | `longtext` | YES | NO | NO | Not recorded |
| 43 | `Nurse5` | `longtext` | YES | NO | NO | Not recorded |
| 44 | `Specialty` | `longtext` | YES | NO | NO | Not recorded |
| 45 | `Sub-specialty` | `longtext` | YES | NO | NO | Not recorded |
| 46 | `Start_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 47 | `End_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 48 | `Surgery_duration` | `longtext` | YES | NO | NO | Not recorded |
| 49 | `PACU_transfer` | `longtext` | YES | NO | NO | Not recorded |
| 50 | `PACU_discharge` | `longtext` | YES | NO | NO | Not recorded |
| 51 | `Return_to_ward` | `longtext` | YES | NO | NO | Not recorded |
| 52 | `qc` | `longtext` | YES | NO | NO | Not recorded |
| 53 | `qc_RN` | `longtext` | YES | NO | NO | Not recorded |
| 54 | `bi_patient` | `longtext` | YES | NO | NO | Not recorded |
| 55 | `QC_diagnosis` | `longtext` | YES | NO | NO | Not recorded |
| 56 | `qc_procedure` | `longtext` | YES | NO | NO | Not recorded |

## Radiology Procedures (`DS_RADIOLOGY_PROCEDURE`)

- Original worksheet: `bi_radiology_procedure d`
- Source table: `stg_ds_radiology_procedure`
- Database schema: `haven_poc_source`
- Number of columns: 39

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `longtext` | YES | NO | NO | Not recorded |
| 2 | `VisitID` | `longtext` | YES | NO | NO | Not recorded |
| 3 | `Test_code` | `longtext` | YES | NO | NO | Not recorded |
| 4 | `Test_description` | `longtext` | YES | NO | NO | Not recorded |
| 5 | `Internal_code` | `longtext` | YES | NO | NO | Not recorded |
| 6 | `Requester` | `longtext` | YES | NO | NO | Not recorded |
| 7 | `Requester_specialty` | `longtext` | YES | NO | NO | Not recorded |
| 8 | `MLT1` | `longtext` | YES | NO | NO | Not recorded |
| 9 | `MLT2` | `longtext` | YES | NO | NO | Not recorded |
| 10 | `MLT3` | `longtext` | YES | NO | NO | Not recorded |
| 11 | `MLT4` | `longtext` | YES | NO | NO | Not recorded |
| 12 | `MLT5` | `longtext` | YES | NO | NO | Not recorded |
| 13 | `Radiologist1` | `longtext` | YES | NO | NO | Not recorded |
| 14 | `Radiologist2` | `longtext` | YES | NO | NO | Not recorded |
| 15 | `Radiologist3` | `longtext` | YES | NO | NO | Not recorded |
| 16 | `Radiologist4` | `longtext` | YES | NO | NO | Not recorded |
| 17 | `Radiologist5` | `longtext` | YES | NO | NO | Not recorded |
| 18 | `Order_urgency` | `longtext` | YES | NO | NO | Not recorded |
| 19 | `Assisting_aids` | `longtext` | YES | NO | NO | Not recorded |
| 20 | `Accession_number` | `longtext` | YES | NO | NO | Not recorded |
| 21 | `Charges` | `longtext` | YES | NO | NO | Not recorded |
| 22 | `Final_report` | `longtext` | YES | NO | NO | Not recorded |
| 23 | `Biomedical_section` | `longtext` | YES | NO | NO | Not recorded |
| 24 | `Modality` | `longtext` | YES | NO | NO | Not recorded |
| 25 | `DurationA` | `longtext` | YES | NO | NO | Not recorded |
| 26 | `DurationB` | `longtext` | YES | NO | NO | Not recorded |
| 27 | `DurationC` | `longtext` | YES | NO | NO | Not recorded |
| 28 | `DurationD` | `longtext` | YES | NO | NO | Not recorded |
| 29 | `DurationE` | `longtext` | YES | NO | NO | Not recorded |
| 30 | `DurationF` | `longtext` | YES | NO | NO | Not recorded |
| 31 | `DurationG` | `longtext` | YES | NO | NO | Not recorded |
| 32 | `idorrimagingrequested` | `longtext` | YES | NO | NO | Not recorded |
| 33 | `requestdate` | `longtext` | YES | NO | NO | Not recorded |
| 34 | `appointmentdate` | `longtext` | YES | NO | NO | Not recorded |
| 35 | `arrivaldate` | `longtext` | YES | NO | NO | Not recorded |
| 36 | `preliminaryreportdate` | `longtext` | YES | NO | NO | Not recorded |
| 37 | `examinationdate` | `longtext` | YES | NO | NO | Not recorded |
| 38 | `finalreportdate` | `longtext` | YES | NO | NO | Not recorded |
| 39 | `__source_column_039` | `longtext` | YES | NO | NO | Not recorded |

## Laboratory Procedures (`DS_LABORATORY_PROCEDURE`)

- Original worksheet: `bi_laboratory_procedure `
- Source table: `stg_ds_laboratory_procedure`
- Database schema: `haven_poc_source`
- Number of columns: 21

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `DeID` | `longtext` | YES | NO | NO | Not recorded |
| 2 | `VisitID` | `longtext` | YES | NO | NO | Not recorded |
| 3 | `Sample_type` | `longtext` | YES | NO | NO | Not recorded |
| 4 | `Sampling_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 5 | `Reception_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 6 | `Lab_location` | `longtext` | YES | NO | NO | Not recorded |
| 7 | `Lab_section` | `longtext` | YES | NO | NO | Not recorded |
| 8 | `Test_code` | `longtext` | YES | NO | NO | Not recorded |
| 9 | `Previous_test` | `longtext` | YES | NO | NO | Not recorded |
| 10 | `Requesterid` | `longtext` | YES | NO | NO | Not recorded |
| 11 | `Requester` | `longtext` | YES | NO | NO | Not recorded |
| 12 | `Requester_specialty` | `longtext` | YES | NO | NO | Not recorded |
| 13 | `Order_urgency` | `longtext` | YES | NO | NO | Not recorded |
| 14 | `Result_datetime` | `longtext` | YES | NO | NO | Not recorded |
| 15 | `DurationA` | `longtext` | YES | NO | NO | Not recorded |
| 16 | `DurationB` | `longtext` | YES | NO | NO | Not recorded |
| 17 | `DurationC` | `longtext` | YES | NO | NO | Not recorded |
| 18 | `Results` | `longtext` | YES | NO | NO | Not recorded |
| 19 | `Range` | `longtext` | YES | NO | NO | Not recorded |
| 20 | `Level` | `longtext` | YES | NO | NO | Not recorded |
| 21 | `idorulabresult` | `longtext` | YES | NO | NO | Not recorded |

## Vital Signs (`DS_VITAL_SIGNS`)

- Original worksheet: `vitalsign data`
- Source table: `stg_ds_vital_signs`
- Database schema: `haven_poc_source`
- Number of columns: 11

| Position | Column name | MySQL column type | Nullable | Primary key | Foreign key | Foreign-key reference |
|---:|---|---|---|---|---|---|
| 1 | `IDVitalSign` | `longtext` | YES | NO | NO | Not recorded |
| 2 | `DeID` | `longtext` | YES | NO | NO | Not recorded |
| 3 | `VisitID` | `longtext` | YES | NO | NO | Not recorded |
| 4 | `TarikhAmbil` | `longtext` | YES | NO | NO | Not recorded |
| 5 | `IsDeleted` | `longtext` | YES | NO | NO | Not recorded |
| 6 | `DateCreated` | `longtext` | YES | NO | NO | Not recorded |
| 7 | `CreatedBy` | `longtext` | YES | NO | NO | Not recorded |
| 8 | `LastUpdate` | `longtext` | YES | NO | NO | Not recorded |
| 9 | `LastUpdateBy` | `longtext` | YES | NO | NO | Not recorded |
| 10 | `StatusProses` | `longtext` | YES | NO | NO | Not recorded |
| 11 | `idpesakitasal` | `longtext` | YES | NO | NO | Not recorded |

## Interpretation notes

- Column order follows the recorded MySQL ordinal position.
- Data types and key indicators are reproduced from the schema inventory.
- A recorded key indicator is metadata, not independent proof that a relationship is valid across all source records.
- Blank, unresolved or unavailable metadata is not replaced with an assumed value.
- Dataset IDs and display labels follow the existing dataset catalogue. The catalogue records wider team confirmation as pending.

## Source files

- `dataset-catalog/dataset_catalog.json`
- `schemas/source_schema_inventory.json`
