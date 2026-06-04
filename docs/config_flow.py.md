# `config_flow.py` — Integration Setup & Re-authentication

## Role

Handles the Home Assistant config flow for the Iotics integration. This is the UI users see when they click "Add Integration" in Settings > Devices & Services.

## Two Steps

### 1. Initial Setup (`async_step_user`)

Shows a form with three fields:

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `email` | Yes | — | Your Iotics account email |
| `password` | Yes | — | Your Iotics account password |
| `appid` | No | `696f74696373617070` | Iotics API app ID (decodes to "ioticsapp") |

When submitted, the flow:
1. Creates an `IoticsApiClient` with the credentials
2. Attempts login via `api.login()`
3. If successful → creates the config entry (integration is added)
4. If failed → shows "cannot_connect" error

### 2. Re-authentication (`async_step_reauth`)

Triggered when the Iotics session token expires. Shows the same form and on success:
1. Updates the existing config entry data
2. Reloads the integration with the new credentials

## Schema

```python
STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_EMAIL): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Optional("appid", default=IOTICS_APPID_DEFAULT): str,
})
```

## Error Messages

Errors are defined in `strings.json` under `config.error`:

| Error key | Display message |
|-----------|-----------------|
| `cannot_connect` | "Failed to connect to the Iotics cloud. Check your email and password." |
