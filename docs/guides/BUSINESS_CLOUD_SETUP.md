# Business Google Cloud / Workspace Cleanup

This runbook keeps the existing project `fabled-sector-476018-n3` and makes it
business-owned before any larger Cloud migration.

## 1. Ownership and billing

- Make the Workspace business admin the primary owner for:
  - Google Cloud project
  - billing account
  - OAuth consent screen
  - service accounts
- Keep one backup admin account.
- Verify whether the project lives under your business Organization or under
  `No organization`.
- If possible, move the project under the business Organization. If that is not
  practical yet, still transfer billing and IAM ownership first.

## 2. IAM baseline

Review and document who currently has these roles:

- `Owner`
- `Project IAM Admin`
- `Service Account Admin`
- `Billing Admin`
- `Storage Admin`
- `Firestore Admin`
- `Logs Viewer`
- `Monitoring Viewer`

Target state:

- business admin = primary admin
- backup admin = secondary admin
- personal account = optional fallback only, not single point of failure
- runtime uses service accounts, not personal login

## 3. Service account baseline

Use one backend service account for:

- Gemini / Vertex
- Firestore
- Cloud Logging
- GCS

Optional later improvement:

- move from raw key files to managed secret or workload identity

If you use Workspace admin actions, enable domain-wide delegation only where it
is actually required.

## 4. OAuth / Workspace

Verify:

- OAuth consent screen belongs to the business project/account
- redirect URIs match your web and local auth flows
- publishing status is correct
- any test-user restrictions are intentional

Workspace integrations should be anchored to the business Workspace identity,
not to a personal Google account as the primary owner.

## 5. APIs, monitoring, and quotas

Confirm these APIs are enabled:

- Vertex AI API / Gemini for Google Cloud API
- Agent Platform API
- Cloud Logging API
- Cloud Firestore API
- IAM API
- Cloud Resource Manager API

Enable operational controls:

- budget alerts
- quota alerts
- log-based alert for `RESOURCE_EXHAUSTED`

Recommended saved Cloud Logging queries:

```text
jsonPayload.event_type="voice_turn_summary"
jsonPayload.event_type="web_chat_request"
jsonPayload.event_type="web_tts_request"
jsonPayload.error:"RESOURCE_EXHAUSTED"
jsonPayload.local_smart_home_fast=true
```

## 6. Runtime configuration policy

Use this location policy:

- `GOOGLE_CLOUD_LOCATION=global` for Gemini text/STT/TTS runtime
- `VERTEX_AI_LOCATION=us-west1` for region-bound services such as RAG/media

Required runtime env values:

- `GOOGLE_APPLICATION_CREDENTIALS`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION`
- `VERTEX_AI_LOCATION`
- `GOOGLE_CUSTOM_SEARCH_CX`
- `FIRECRAWL_API_KEY`

## 7. Acceptance checklist

- business billing owns the project
- business admin and backup admin can access Cloud + Workspace
- service account can access backend services without personal login
- Cloud Logging and Firestore work under the business-owned setup
- runtime env matches the location and credential policy above
