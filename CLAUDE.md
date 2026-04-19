# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build, lint, validate

- **flake8** — `.flake8` sets `max-line-length = 120` and excludes `.git,.github,docs,venv,.venv`. Run with `.venv/bin/python -m flake8 custom_components`.
- **hassfest** — Home Assistant's manifest/translations validator. Runs in CI (`hassfest.yaml`); locally it needs a HA dev environment, so in practice rely on CI or a HA core checkout.
- **HACS action** — validates the repo is HACS-compatible (`hacs.yaml`, `hacs.json`).

Releases: creating a GitHub release triggers `.github/workflows/release.yaml`, which rewrites `manifest.json`'s `version` to the tag name, zips `custom_components/umweltbundesamt/` into `umweltbundesamt.zip`, and attaches it to the release. The `version` value in `manifest.json` on `main` is therefore advisory — the release tag wins.

Directory casing: the integration domain (and therefore the `custom_components/<domain>/` directory) is lowercase `umweltbundesamt` because Home Assistant requires domains to match `^[a-z_]+$`.

## Architecture

The integration follows HA's standard **config entry + coordinator + platforms** pattern, with a thin domain layer under `api/` that isolates Umweltbundesamt-specific logic from HA concerns.

## Home Assistant Development Reference

- **Integration development:** https://developers.home-assistant.io/docs/development_index/
- **Manifest requirements:** https://developers.home-assistant.io/docs/creating_integration_manifest/
- **Config flow:** https://developers.home-assistant.io/docs/config_entries_config_flow_handler/
- **Entity conventions:** https://developers.home-assistant.io/docs/core/entity/
- **HACS integration publishing:** https://hacs.xyz/docs/publish/integration/
- **HACS plugin publishing:** https://hacs.xyz/docs/publish/plugin/
- **HACS validation action:** https://hacs.xyz/docs/publish/action/
