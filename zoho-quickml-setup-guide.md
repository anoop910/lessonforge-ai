# Zoho Catalyst QuickML: Endpoint Setup and Credentials Guide

This guide covers how to create a QuickML endpoint, get the credentials needed to call it, and call it using REST, the Python SDK, or LangChain.

> **Data center note:** Examples use the **India** data center (`.in`). If your account is on another region, replace `.in` with `.com`, `.eu`, or `.com.au` as appropriate.

---

## 1. Overview

There are two ways to call a QuickML endpoint:

| Method | When to use | Auth |
|---|---|---|
| **REST API** | Any language or app outside Catalyst | `Authorization: Zoho-oauthtoken <access-token>` header |
| **Catalyst SDK** (Python / JavaScript / Java) | Python, JS or Java apps | SDK handles tokens if you give it a refresh token |

QuickML has two main endpoint types:

- **Pipeline (ML model) endpoints:** predictions from a trained model using table-style input.
- **LLM Serving endpoints:** hosted large language models (for example GLM-4.7-Flash) under *Generative AI*.

---

## 2. Create the Endpoint

1. Sign in to the **Catalyst console** and open your project.
2. Open **QuickML**.
3. Train and save your model (pipeline), or configure a model under **Generative AI → LLM Serving**.
4. Create an **Endpoint** for the saved model/configuration and **publish** it.
5. Open the endpoint's **details page**. It shows:
   - Endpoint URL
   - Required headers
   - A sample request and response
   - The **Endpoint Key** (used by the SDK)

> The model and its parameters are fixed when the endpoint is created. They cannot be overridden later through the SDK.

---

## 3. Get Credentials (OAuth)

The REST API needs an OAuth **access token**. The simplest way for server-to-server use is a **Self Client**.

### 3.1 Create a Self Client

1. Open the Zoho API Console: **https://api-console.zoho.in**
2. Click **Add Client** and choose **Self Client**.
3. Open the **Client Secret** tab and copy your **Client ID** and **Client Secret**.

### 3.2 Generate a Grant Code

In the Self Client's **Generate Code** tab:

- **Scope:** `QuickML.deployment.READ` (check the QuickML docs in case your endpoint needs an additional scope; the SDK's *Execute* operations may need a broader scope)
- **Time duration:** up to 10 minutes
- **Scope description:** anything

Click **Create** and copy the code immediately.

> A grant code works **only once** and expires after the duration you chose.

### 3.3 Exchange the Grant Code for Tokens

Send a `POST` request from your terminal or Postman.

```bash
curl -X POST "https://accounts.zoho.in/oauth/v2/token" \
  -d "grant_type=authorization_code" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "code=<GRANT_CODE>"
```

**Postman:** method `POST`, URL `https://accounts.zoho.in/oauth/v2/token`, Body → **x-www-form-urlencoded** with the four keys above.

Response:

```json
{
  "access_token": "1000.xxxx.yyyy",
  "refresh_token": "1000.aaaa.bbbb",
  "expires_in": 3600,
  "api_domain": "https://www.zohoapis.in",
  "token_type": "Bearer"
}
```

**Save the `refresh_token`.** It does not expire and is used to get new access tokens.

### 3.4 Get a New Access Token (every hour)

Access tokens last **1 hour**.

```bash
curl -X POST "https://accounts.zoho.in/oauth/v2/token" \
  -d "grant_type=refresh_token" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "refresh_token=<REFRESH_TOKEN>"
```

### 3.5 Other Values You May Need

| Value | Where to find it |
|---|---|
| **Org ID** (`CATALYST-ORG` header) | Catalyst console → project settings |
| **Project ID** | Catalyst console → project settings |
| **ZAID** (used as `project_key` in the SDK) | Catalyst console → project settings |
| **Endpoint Key** | QuickML endpoint details page |
| **Endpoint URL** | QuickML endpoint details page |

---

## 4. Call the Endpoint with REST

```bash
curl -X POST "<ENDPOINT_URL>" \
  -H "Authorization: Zoho-oauthtoken <ACCESS_TOKEN>" \
  -H "CATALYST-ORG: <ORG_ID>" \
  -H "Content-Type: application/json" \
  -d '{ ... }'
```

Use the exact URL, headers, and body format shown on your endpoint's details page.

### Python helper: auto-refresh the token

```python
import os, time, requests

TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"
_cache = {"token": None, "expires_at": 0}

def get_access_token():
    # reuse the cached token until 5 minutes before expiry
    if _cache["token"] and time.time() < _cache["expires_at"] - 300:
        return _cache["token"]

    r = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": os.environ["ZOHO_CLIENT_ID"],
        "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
        "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
    })
    data = r.json()
    _cache["token"] = data["access_token"]
    _cache["expires_at"] = time.time() + data.get("expires_in", 3600)
    return _cache["token"]

def call_endpoint(url, payload):
    headers = {
        "Authorization": f"Zoho-oauthtoken {get_access_token()}",
        "CATALYST-ORG": os.environ["CATALYST_ORG_ID"],
        "Content-Type": "application/json",
    }
    return requests.post(url, headers=headers, json=payload).json()
```

---
