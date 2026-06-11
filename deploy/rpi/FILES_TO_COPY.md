# Files To Copy To Raspberry Pi

## Must copy

### 1. Repo

Copy or clone the whole repo to:

```text
/opt/google-clause
```

### 2. Service account key

Copy:

```text
service_account_key.json
```

To:

```text
/opt/google-clause/secrets/service_account_key.json
```

This is needed for:
- Vertex AI
- Firestore
- Google Cloud client libraries that use service account auth

### 3. OAuth token file

If you can find it, copy:

```text
tokens.json
```

To:

```text
/opt/google-clause/state/oauth/tokens.json
```

Most likely source locations on your current machine:
- `%USERPROFILE%\\.google_workspace_adk\\tokens.json`
- project root `tokens.json`
- `auth\\token.json`
- `.auth\\token.json`

## Optional but useful

### 4. OAuth client credentials JSON

If you cannot find `tokens.json`, copy:

```text
oauth_client_credentials.json
```

To:

```text
/opt/google-clause/oauth_client_credentials.json
```

This file is not required for normal runtime if env vars already contain:
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`

But it is useful if you need to generate a fresh OAuth token on the Pi with:

```bash
python scripts/force_oauth_login.py
```

## Not needed for runtime

### `firestore.indexes.json`

You do not need this file on the Pi for normal app runtime.

It is only relevant when:
- managing Firestore indexes
- deploying Firestore configuration
- keeping infra config under version control

## Recommended permissions on Pi

```bash
mkdir -p /opt/google-clause/secrets
chmod 700 /opt/google-clause/secrets
chmod 600 /opt/google-clause/secrets/service_account_key.json
chmod 600 /opt/google-clause/state/oauth/tokens.json
```
