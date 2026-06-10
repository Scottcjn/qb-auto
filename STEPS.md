# QuickBooks Online API Setup

This repo now includes [`qbo_api.py`](/home/scott/qb-auto/qbo_api.py), a minimal production client for the QuickBooks Online Accounting API.

## 1. Create or open the Intuit app

1. Sign in to the Intuit Developer Portal.
2. Open the production app for Elyan Labs, or create one if needed.
3. Enable the QuickBooks Online Accounting scope:
   - `com.intuit.quickbooks.accounting`
4. Do not add `com.intuit.quickbooks.payment` unless you later need direct Payments API work. It is not required for recurring-template queries, deletes, or invoice voids.

## 2. Set the production redirect URI

1. In the app, open `Settings` -> `Redirect URIs`.
2. Add a production redirect URI.
3. Production redirect URIs must be `https://...`.
4. Intuit does not allow plain `http://` or raw IPs for production redirects.

Example:

```text
https://YOUR-DOMAIN.example/qbo/oauth/callback
```

If you do not have a permanent callback yet, use a temporary HTTPS endpoint you control, capture the query string once, and then exchange the code manually.

## 3. Copy the 4 credentials Scott needs

From the Intuit app dashboard / keys area, collect:

- `QBO_CLIENT_ID`
- `QBO_CLIENT_SECRET`
- `QBO_REALM_ID`
- `QBO_REFRESH_TOKEN`

Notes:

- `realmId` is returned on the OAuth callback URL after authorization.
- `refresh_token` is returned by the token exchange call.
- Intuit rotates refresh tokens. Persist the newest `refresh_token` whenever you refresh or reauthorize.

## 3b. FAST PATH for first refresh_token — OAuth Playground

Easiest way to get the **first** refresh_token without standing up a callback server:

1. Open https://developer.intuit.com/app/developer/playground
2. Pick your app from the dropdown.
3. Pick scope `com.intuit.quickbooks.accounting`.
4. Click **Get authorization code** — opens an Intuit consent page.
5. Sign in as the QBO admin for the company you want to drive (your sandbox uses the auto-created sample company; for production use the real Wachter QBO admin).
6. Click **Connect**. The playground redirects back and shows the authorization code + realmId.
7. Click **Get tokens** — playground exchanges the code and shows `access_token` + `refresh_token`.
8. Copy `refresh_token` into `.env` as `QBO_REFRESH_TOKEN`. The realmId is already in `.env` for sandbox (`9341456505413084`); for production, copy the new realmId shown.

The redirect URI used by the playground is pre-registered for every dev app, so step 2 (custom redirect URI) is not needed when you use this path.

## 4. Run the one-time production OAuth authorize flow (alternative)

Set local shell vars first:

```bash
export QBO_CLIENT_ID='...'
export QBO_CLIENT_SECRET='...'
export REDIRECT_URI='https://YOUR-DOMAIN.example/qbo/oauth/callback'
export STATE='elyan-qbo-prod-001'
```

Build the authorize URL:

```text
https://appcenter.intuit.com/connect/oauth2?client_id=YOUR_CLIENT_ID&response_type=code&scope=com.intuit.quickbooks.accounting&redirect_uri=YOUR_URLENCODED_REDIRECT_URI&state=YOUR_STATE
```

Open that URL in a browser while signed in as the QuickBooks Online admin for the Wachter company.

After consent, Intuit redirects to:

```text
https://YOUR-DOMAIN.example/qbo/oauth/callback?code=...&state=...&realmId=...
```

Copy:

- `code`
- `realmId`

## 5. Exchange the authorization code for tokens

```bash
export CODE='PASTE_AUTH_CODE'
export QBO_REALM_ID='PASTE_REALMID'

curl -u "$QBO_CLIENT_ID:$QBO_CLIENT_SECRET" \
  -X POST 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=authorization_code' \
  --data-urlencode "code=$CODE" \
  --data-urlencode "redirect_uri=$REDIRECT_URI"
```

From the JSON response, save:

- `refresh_token` -> `QBO_REFRESH_TOKEN`
- `access_token` is short-lived and does not need to be stored long-term

## 6. Export env vars for this repo

```bash
export QBO_CLIENT_ID='...'
export QBO_CLIENT_SECRET='...'
export QBO_REFRESH_TOKEN='...'
export QBO_REALM_ID='...'
```

## 7. Test the client

From `/home/scott/qb-auto`:

```bash
python3 - <<'PY'
import json
import qbo_api

print(json.dumps(qbo_api.get_company_info(), indent=2))
PY
```

Useful next checks:

```bash
python3 - <<'PY'
import json
import qbo_api

print(json.dumps(qbo_api.list_recurring(), indent=2))
PY
```

```bash
python3 - <<'PY'
import json
import qbo_api

print(json.dumps(qbo_api.query_invoices_by_customer("Wachter"), indent=2))
PY
```

## 8. Manual refresh-token test

```bash
curl -u "$QBO_CLIENT_ID:$QBO_CLIENT_SECRET" \
  -X POST 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=refresh_token' \
  --data-urlencode "refresh_token=$QBO_REFRESH_TOKEN"
```

Persist the newest `refresh_token` returned by Intuit.
