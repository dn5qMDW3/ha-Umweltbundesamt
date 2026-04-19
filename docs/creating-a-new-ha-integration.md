# Creating a new Home Assistant custom integration

A practical, opinionated checklist for shipping a HACS-installable HA integration from scratch. Distilled from building this repo. Reference the upstream docs for anything marked **[docs]**.

---

## 0. Decide before you type

1. **What does your integration do?** Pick exactly one: poll a cloud API (`iot_class: cloud_polling`), push-subscribe to a cloud (`cloud_push`), talk to a local device (`local_polling` / `local_push`), or consume already-discovered data (`calculated`).
2. **Domain name** — lowercase, `^[a-z_]+$`. This is the directory name, module name, and `manifest.json["domain"]`. Cannot be changed after release.
3. **Integration type** — `device` (one device per entry), `hub` (one device per entry that owns many child entities), or `service` (cloud service keyed by account). [docs: [manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/#integration-type)]
4. **Config entry schema** — write out what the user needs to pick at install time (host? account? station?). This becomes your config flow.
5. **Entity catalog** — list every sensor / switch / binary_sensor you'll create. For each, pick a HA `device_class` if one fits. Missing device classes are a strong signal to simplify, not invent.

Write these four answers in a spec file before you write code. Keep it to one page.

---

## 1. Project scaffold

```
<repo-root>/
├── .flake8                          # max-line-length = 120, extend-ignore = E203,W503
├── .github/workflows/
│   ├── hassfest.yaml                # uses home-assistant/actions/hassfest@master
│   ├── hacs.yaml                    # uses hacs/action@main with category: integration
│   └── release.yaml                 # auto-release on manifest version bump (see §9)
├── .gitignore                       # at minimum .venv/, __pycache__/, .pytest_cache/
├── README.md                        # HACS renders this on the integration card
├── hacs.json                        # HACS manifest: {"name": "...", "homeassistant": "2025.1.0"}
├── pyproject.toml                   # [tool.pytest.ini_options] asyncio_mode = "auto"
├── custom_components/<domain>/
│   ├── __init__.py                  # async_setup_entry / async_unload_entry
│   ├── manifest.json                # see §2
│   ├── const.py                     # DOMAIN, config keys, scan interval
│   ├── config_flow.py               # see §4
│   ├── coordinator.py               # see §5
│   ├── sensor.py (or other platform) # see §6
│   ├── strings.json                 # canonical EN translation source
│   ├── translations/<lang>.json     # other languages
│   └── api/                         # optional: thin client that knows nothing about HA
│       ├── client.py
│       ├── models.py                # dataclasses
│       └── errors.py
└── tests/
    ├── conftest.py
    ├── fixtures/                    # JSON recordings from the real API
    └── test_*.py
```

### Virtual environment

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install homeassistant pytest-homeassistant-custom-component \
                      aiohttp aioresponses flake8
```

Always use `.venv/bin/python` / `.venv/bin/pip`. Never install HA globally.

---

## 2. `manifest.json`

Minimum viable manifest:

```json
{
  "domain": "<your_domain>",
  "name": "Display Name",
  "codeowners": ["@your-github-handle"],
  "config_flow": true,
  "documentation": "https://github.com/<you>/<repo>",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/<you>/<repo>/issues",
  "quality_scale": "bronze",
  "requirements": [],
  "version": "0.1.0"
}
```

- **`codeowners`** — must be non-empty (HACS validation). Use `@your-github-handle`.
- **`integration_type`** — **`hub`** if one config entry spawns multiple entities under one device; **`device`** for one-to-one; **`service`** for cloud accounts. The default is `service` — usually wrong.
- **`iot_class`** — `cloud_polling` is right when you hit an HTTPS API. `local_polling` if the device is on LAN.
- **`requirements`** — list `PyPI==pinned` only for libs HA core doesn't already ship. `aiohttp`, `voluptuous`, `homeassistant` itself, helpers — all ship with HA. Leave `requirements` empty if you don't have additional deps.
- **`version`** — advisory on `main`; the release tag becomes the source of truth (see §9).
- **`quality_scale`** — declare after you've met the rules for the scale you claim. [docs: [quality scale](https://developers.home-assistant.io/docs/integration_quality_scale/)]

[docs: [creating_integration_manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)]

---

## 3. `hacs.json`

Keep it minimal — the HACS docs are very short for a reason.

```json
{
  "name": "Display Name",
  "homeassistant": "2025.1.0"
}
```

- **`homeassistant`** — minimum HA version you're promising to support. Bump this any time you use an API introduced in a newer release (e.g. `ConfigEntry.runtime_data` in 2024.11+). Too low = users on old HA install and get `ImportError`s at entry setup.
- Don't add `content_in_root: false` — it's the default.
- Don't add `render_readme: true` — it's deprecated.
- `zip_release` / `filename` are only for repos that ship a pre-built zip instead of the source tree.

[docs: [HACS integration publishing](https://hacs.xyz/docs/publish/integration/), [HACS manifest](https://www.hacs.xyz/docs/publish/start/)]

---

## 4. Config flow

Patterns you want from day one:

```python
class YourConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(stable_id_from_input)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=title, data=data, options=options,
            )
        return self.async_show_form(
            step_id="user", data_schema=_build_schema(...),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return YourOptionsFlow()           # no-arg, not (entry)


class YourOptionsFlow(config_entries.OptionsFlow):
    # No __init__. Access self.config_entry (built-in property).

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        ...
```

Things to get right:

- **`unique_id`** — call `async_set_unique_id(str(...))` + `_abort_if_unique_id_configured()` before `async_create_entry`. Without this, users can add the same device twice.
- **Errors vs. aborts** — `async_show_form(errors={...})` keeps the form open (user can retry); `async_abort(reason=...)` ends the flow. Put transient network failures in `abort` with a `cannot_connect` reason rather than blocking the form.
- **Selectors** — `SelectSelector(SelectSelectorConfig(options=[SelectOptionDict(value=str(...), label="..."), ...], mode=DROPDOWN, custom_value=False))`. The `value` fields **must be strings**. If you need an int at storage time, wrap the schema: `vol.All(vol.Coerce(str), SelectSelector(...), lambda v: int(v))`, and pass `default=str(int_default)` — a mismatched default type is a common source of "Config flow could not be loaded: 500" errors.
- **Translations** — `async_show_form` does not need an `errors=` for abort reasons, but every `errors`/`abort` reason you use **must** exist under `config.error.<key>` or `config.abort.<key>` in `strings.json`.
- **No `__init__(self, entry)` on `OptionsFlow`** — this pattern is deprecated since HA 2024.11 and errors from 2025.12 onward. Use the built-in `self.config_entry` property.
- **Don't swallow `AbortFlow`** — if you wrap the step body in a broad `try/except`, re-raise `AbortFlow` explicitly (it's the internal signal used by `_abort_if_unique_id_configured`). Better: don't wrap at all; HA already maps unhandled exceptions to an `unknown` abort.

[docs: [config flow handler](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/), [options flow change](https://developers.home-assistant.io/blog/2024/11/12/options-flow/)]

---

## 5. Coordinator

One `DataUpdateCoordinator` per config entry is the standard shape for polling integrations. It deduplicates fetches across listeners and gives you `UpdateFailed` / `last_update_success` for free.

```python
class YourCoordinator(DataUpdateCoordinator[Measurement]):
    def __init__(self, hass, client, ...):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{identifier}",
            update_interval=SCAN_INTERVAL,
        )
        self._client = client

    async def _async_update_data(self) -> Measurement:
        try:
            return await self._client.fetch_current()
        except YourAPIError as err:
            raise UpdateFailed(str(err)) from err
```

- Do **not** catch and log inside `_async_update_data`; raise `UpdateFailed` and the base class logs at the right level.
- Entities inherit from `CoordinatorEntity[YourCoordinator]`; they go `unavailable` automatically on `UpdateFailed`.

---

## 6. `__init__.py`: setup, unload, runtime_data

The modern (post-HA 2024.11) pattern stores per-entry state on `entry.runtime_data`, **not** in `hass.data[DOMAIN][entry.entry_id]`.

```python
@dataclass
class YourRuntimeData:
    client: YourClient
    coordinator: YourCoordinator


type YourConfigEntry = ConfigEntry[YourRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: YourConfigEntry) -> bool:
    client = YourClient(async_get_clientsession(hass))
    coordinator = YourCoordinator(hass, client, ...)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = YourRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
```

Platforms then read `entry.runtime_data.coordinator` / `.client` directly — no shared dict, no string keys. Runtime data is cleared automatically on unload.

This pattern is required for `quality_scale: bronze`.

---

## 7. Entities

[docs: [entity conventions](https://developers.home-assistant.io/docs/core/entity/)]

```python
class YourSensor(CoordinatorEntity[YourCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "something"          # resolves via strings.json
    _attr_device_class = SensorDeviceClass.XYZ   # if one fits
    _attr_state_class = SensorStateClass.MEASUREMENT  # unlocks long-term stats

    def __init__(self, coordinator, ...):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{stable_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, stable_device_key)},
            name=..., manufacturer=..., model=...,
        )

    @property
    def native_value(self):
        return self.coordinator.data.something
```

- **`_attr_has_entity_name = True`** is mandatory now. It lets the UI combine "Device name + Entity name" automatically.
- **Set `device_class` whenever one fits**, and **omit `_attr_name`** for those — HA will localize the entity name from the device class. Only set `_attr_name` or `_attr_translation_key` for values HA doesn't know about.
- **`state_class = MEASUREMENT`** is how HA's recorder decides to keep long-term statistics. If your sensor is a count of things over time, `TOTAL_INCREASING` is usually right.
- **`unique_id`** — must be stable across restarts and unique per HA instance. Prefix with the domain, then a scoped key (device id + entity role). Don't include the entity's friendly name.
- **`DeviceInfo.identifiers`** — `{(DOMAIN, "<string unique to this device>")}`. Any per-device metadata (name, manufacturer, model, configuration_url) lives here, not on the entity.
- **Don't override `_handle_coordinator_update`** unless you need to filter. `CoordinatorEntity` already calls `async_write_ha_state` on each update.
- **`extra_state_attributes`** — use sparingly. HA prefers dedicated entities over attribute blobs. If an attribute is interesting enough to chart or alert on, give it its own entity.

---

## 8. Translations

`strings.json` is the canonical EN source. Other languages live in `translations/<lang>.json`.

Keys HA looks up:

- `config.step.<step_id>.title` / `.description` / `.data.<field>`
- `config.abort.<reason>` / `config.error.<key>`
- `options.step.<step_id>.*` (same structure)
- `entity.<platform>.<translation_key>.name` — matches `_attr_translation_key`
- `entity.<platform>.<translation_key>.state_attributes.<attr>.name` — label for an attribute

Any reason you pass to `async_abort` or `errors=` **must** have a matching string, otherwise HA shows the raw key in the UI.

---

## 9. Release workflow (auto-release on version bump)

Trigger a release by bumping `manifest.json`'s `version` and pushing to `main`. No manual tag-cutting:

```yaml
# .github/workflows/release.yaml
name: Release on manifest version bump
on:
  push:
    branches: [main]
    paths: ["custom_components/<domain>/manifest.json"]
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: { fetch-depth: 0 }
      - id: version
        run: |
          v=$(python -c "import json; print(json.load(open('custom_components/<domain>/manifest.json'))['version'])")
          echo "tag=v$v" >> "$GITHUB_OUTPUT"
      - id: tag_check
        run: |
          if git rev-parse -q --verify "refs/tags/${{ steps.version.outputs.tag }}"; then
            echo "exists=true" >> "$GITHUB_OUTPUT"
          else
            echo "exists=false" >> "$GITHUB_OUTPUT"
          fi
      - if: steps.tag_check.outputs.exists == 'false'
        run: |
          cd custom_components/<domain>
          zip -r "$GITHUB_WORKSPACE/<domain>.zip" .
      - if: steps.tag_check.outputs.exists == 'false'
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.version.outputs.tag }}
          name: ${{ steps.version.outputs.tag }}
          target_commitish: ${{ github.sha }}
          generate_release_notes: true
          files: <domain>.zip
```

The tag-exists check makes the workflow idempotent — editing unrelated things in `manifest.json` won't spam releases.

---

## 10. CI workflows

### `hassfest.yaml`

```yaml
name: Validate with hassfest
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: home-assistant/actions/hassfest@master
```

### `hacs.yaml`

```yaml
name: HACS Validation
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: hacs/action@main
        with: { category: integration }
```

[docs: [HACS validation action](https://hacs.xyz/docs/publish/action/)]

---

## 11. Tests

`pytest-homeassistant-custom-component` gives you a real `hass` fixture, entity registries, config-entry helpers, and network blocking. Required setup:

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

```python
# tests/conftest.py
import pytest
pytest_plugins = ["pytest_homeassistant_custom_component"]

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
```

Tests you should have on day one:

- **API client** — feed fixtures via `aioresponses`, assert parsing + error mapping. One fixture per notable response shape. **Record fixtures from the real API, don't invent them** — this is the single most common source of real-world bugs.
- **Coordinator** — inject an `AsyncMock` client, assert `UpdateFailed` on API errors and `data` cached on success.
- **Config flow** — happy path, `cannot_connect`, duplicate rejection, and at least one options-flow scenario.
- **Entities** — instantiate via a full `async_setup_entry`, assert state/unit/device_class on the real entity in `hass.states`. Don't assert entity IDs character-for-character — HA's slugification is opinionated; use the unique_id or filter `hass.states.async_all` instead.

Common gotchas:

- `ConfigEntry(...)` gains required kwargs each HA release (`discovery_keys={}`, `subentries_data={}` etc.). Update test helpers when the HA version moves.
- `MagicMock(name=...)` doesn't set `.name` — `name` is reserved on `Mock`. Build the mock, then `m.name = "..."`.
- HA canonicalizes `µ` (U+00B5) to `μ` (U+03BC) in units. Don't assert on the exact codepoint.

---

## 12. Release checklist

Before cutting `v1.0.0`:

- [ ] `hassfest` and HACS CI passing.
- [ ] All tests passing, flake8 clean.
- [ ] Manually install via HACS as a custom repository in a clean HA test instance, verify the config flow, verify entities appear and update.
- [ ] `README.md` lists: what the integration does, which entities it creates, installation via HACS, any required configuration, and the data source / license attribution.
- [ ] Submit a PR to [`home-assistant/brands`](https://github.com/home-assistant/brands) with `custom_integrations/<domain>/icon.png` (256×256) and `logo.png` (≤512×512) so the HA UI shows a proper logo.
- [ ] `quality_scale` in the manifest reflects what you've actually implemented.

After the first release:

- [ ] Announce in the HACS `#integrations` channel on the HA Discord, or on the HA Community forum.
- [ ] Optionally PR to the [HACS default repositories list](https://github.com/hacs/default) so users can install it without adding your repo as a custom repository first.

---

## Appendix: references

- HA developer portal: https://developers.home-assistant.io/docs/development_index/
- Manifest reference: https://developers.home-assistant.io/docs/creating_integration_manifest/
- Config flow handler: https://developers.home-assistant.io/docs/config_entries_config_flow_handler/
- Entity conventions: https://developers.home-assistant.io/docs/core/entity/
- Integration quality scale: https://developers.home-assistant.io/docs/integration_quality_scale/
- HACS integration publishing: https://hacs.xyz/docs/publish/integration/
- HACS validation action: https://hacs.xyz/docs/publish/action/
- Brands repo: https://github.com/home-assistant/brands
