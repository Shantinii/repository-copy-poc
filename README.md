# Data Safe Haven: Repository-Copy POC

## Purpose

This repository contains selected scripts and documentation for the local Data Safe Haven repository-copy proof of concept.

## Included

- MySQL repository-copy workflow and validation logic.
- Supporting tests for destination safety and copy behaviour.
- Repository-copy design and handover documentation.

## Scope and limitations

This is a local proof of concept, not a production service. It does not provide a frontend API, verify real payment-provider events, or implement the complete researcher-to-LLM workflow.

The scripts require an appropriately configured local MySQL environment. Do not run them against production or real clinical data.

## Setup

Install the Python dependencies required by the scripts and configure database credentials locally. Do not commit `.env` files, credentials, workbooks, clinical data, or database exports.

Review each script and its test instructions before running it.

## Phase 1 workflow

The Phase 1 implementation includes:

- Inspection and mapping of all 10 approved workbook worksheets.
- Raw staging of 1,000 sample rows across 10 MySQL staging tables.
- Read-only verification comparing all staged rows and columns against the workbook.
- Selected relational loading for Patient, Visit, and Diagnosis.
- Fixed clinical repository copying for those three tables.

The latest recorded staging verification confirmed that all 10 staging tables matched the workbook, covering 1,000 rows and 310 columns.

## Phase 1 documentation

- `docs/phase1_handover.md` - Implementation details, validation evidence, findings, and outstanding items.
- `docs/repository_copy_design.md` - Repository-copy design.
- `data_dictionary.md` - Dataset and column inventory.
- `dataset-catalog/` - Dataset catalogue and ID mapping.
- `schemas/` - Source schema metadata.
- `reports/` - Staging manifest.

Dynamic researcher-specific provisioning, frontend and payment integration, and complete LLM integration are outside the implemented Phase 1 scope.
