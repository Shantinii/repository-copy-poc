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
