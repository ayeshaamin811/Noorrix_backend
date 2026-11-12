# Sell My Car API — Frontend Integration Guide

Base URL: `https://noorrix-backend-production.up.railway.app` in production, `http://127.0.0.1:8000` locally.

Front end: the `/sell-my-car` page. Every API call is in `src/lib/sellMyCar.js`.

**Status:** the backend is live. The vehicle lookup can use two free government APIs:

- **DVLA Vehicle Enquiry Service** gives the make, year, colour and fuel, but not the model. It needs `DVLA_API_KEY`, which we have.
- **DVSA MOT History API** gives the make, model, year, colour and fuel. It needs `DVSA_TOKEN_URL`, `DVSA_CLIENT_ID`, `DVSA_CLIENT_SECRET` and `DVSA_API_KEY` from DVSA's approval email. We don't have these yet.

When all the DVSA values are set, DVSA is asked first. If DVSA doesn't return the car, or is down, the details come from DVLA and `model` is `null`. Until DVSA is set up, `model` is always `null` and staff ask the customer for it when they call. Adding the DVSA values needs no code change. If neither API is set up, the lookup returns `503` and the customer carries on without car details.

---

## Connect the front end

No front-end code change is needed. `src/lib/sellMyCar.js` already calls these URLs. The page's time slots, photo limits and phone format were compared with the backend rules and they match.

### 1. Run both apps locally

Backend, with `DEBUG=True` and `DVLA_API_KEY` in `.env`. `DEBUG=True` allows all origins:

```bash
python manage.py migrate
python manage.py runserver 8000
```

Front end, in `.env.local`:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Remove `NEXT_PUBLIC_SELL_MY_CAR_DEMO=true` if it is there, then restart `npm run dev`.

### 2. Check it end to end

**Real emails are sent if `RESEND_API_KEY` is set in the backend's `.env`**, so use an email address you own. Submissions are limited to 10 per hour per IP. Restarting the backend resets the count locally.

- [ ] A real registration shows the confirm screen with the make, year, colour and fuel.
- [ ] Once the DVSA values are added, a real registration also shows the model.
- [ ] Without `DVLA_API_KEY`, the lookup moves on without car details.
- [ ] A complete submission shows the confirmation screen.
- [ ] The enquiry appears in Django admin under **Sell my car enquiries**, with its make and photos.
- [ ] The owner email arrives with the details and photo links, and replying goes to the customer.
- [ ] The customer email arrives and doesn't mention a price.
- [ ] A booked slot shows as unavailable on that date.
- [ ] Cancelling the enquiry in admin frees its slot.
- [ ] Two people booking the same slot gets the second one the "just been booked" message.
- [ ] A file that isn't really an image shows an error on the form.

---

## Endpoints

No login or `Authorization` header is needed on any of these.

| Method | Endpoint | Description | Success |
|--------|----------|-------------|---------|
| GET | `/api/sell-my-car/lookup/?reg=AB12CDE&mileage=10220` | Look up the car with DVSA and DVLA | `200` |
| GET | `/api/sell-my-car/availability/?date=2026-11-03` | Booked inspection slots for a date | `200` |
| POST | `/api/sell-my-car/` | Submit the car and book a slot | `201` |

---

## `GET /api/sell-my-car/lookup/`

| Param | Rules |
|-------|-------|
| `reg` | Uppercase with no spaces, 2 to 7 letters or digits |
| `mileage` | Whole number from 1 to 9,999,999. Validated but not used for the lookup |

A successful lookup returns these five fields. `model` is `null` when the details came from DVLA, because DVLA doesn't provide it.

```json
{ "make": "CITROEN", "model": "C3", "year": 2009, "colour": "SILVER", "fuel_type": "DIESEL" }
{ "make": "CITROEN", "model": null, "year": 2009, "colour": "SILVER", "fuel_type": "DIESEL" }
```

- `year` is a number, the year of manufacture.
- Text values come in capitals, as the government APIs send them. The page's `vehicleTitle` already turns them into "Citroen" and "Silver".
- Any field the API doesn't have is `null`.

| Response | Body | What the front end does |
|----------|------|-------------------------|
| `200` with make | The fields above | Shows the confirm screen |
| `200` | `{}` | Neither API has a record, so it skips the confirm screen |
| `400` | `{ "error": "Please enter a valid registration." }` | Stops on step 1 and shows the message |
| `404` | `{ "error": "We couldn't find a vehicle with that registration." }` | DVLA rejected the registration's format. Stops on step 1 and shows the message |
| `429` | `{ "error": "Too many requests. Please try again later." }` | Carries on without car details |
| `503` | `{ "error": "Vehicle lookup is temporarily unavailable." }` | Carries on without car details |

Limited to 30 requests per hour per IP. The API never returns `body_type`, `transmission` or `estimated_value`, because no free API provides them, so those parts of the page stay hidden.

---

## `GET /api/sell-my-car/availability/`

```json
{ "date": "2026-11-03", "booked_times": ["10:00", "14:30"] }
```

Cancelled enquiries are left out, so their slots show as free. A missing or malformed `date` returns `400` with `{ "error": "..." }`.

---

## `POST /api/sell-my-car/`

Send `multipart/form-data`.

| Field | Example | Rules |
|-------|---------|-------|
| `reg` | `AB12CDE` | Same as the lookup |
| `mileage` | `10220` | Same as the lookup |
| `name` | `Alex Smith` | Trimmed, 2 to 150 characters |
| `email` | `alex@example.com` | Valid email |
| `phone` | `+447701910159` | UK number in E.164 format. 03 and 08 numbers are rejected |
| `address` | `1 High Street, Bedford MK40 1AA` | Trimmed, 5 to 300 characters |
| `message` | | Optional, up to 2000 characters |
| `appointment_date` | `2026-11-03` | From today to today + 6 days, UK time |
| `appointment_time` | `12:00` | 30-minute slot start from `09:00` to `17:30`, not already started if the date is today |
| `images` | files, repeated key | Optional, up to 10, each up to 10MB, PNG, JPEG, GIF or WEBP |

The file's real format is checked, so a renamed file is rejected. The make and model are looked up by the backend and are not sent. If the lookup fails, the enquiry is still saved without them.

| Response | Body |
|----------|------|
| `201` | `{ "success": true, "id": 12, "message": "Thanks! Our team will review your details and email you an offer." }` |
| `400` | `{ "success": false, "errors": { "phone": ["Please enter a valid UK phone number."] } }` |
| `409` | `{ "error": "This time slot has just been booked. Please pick another." }` |
| `429` | `{ "error": "Too many requests. Please try again later." }` |

Limited to 10 requests per hour per IP, and rejected submissions count towards this.

### Validation messages

Each value in `errors` is a flat list of strings, under the field names above.

| Field | Message |
|-------|---------|
| `reg` | Please enter a valid registration. |
| `mileage` | Please enter your mileage as a whole number from 1 to 9,999,999. |
| `name` | Please enter your name (2 to 150 characters). |
| `email` | Please enter a valid email address. |
| `phone` | Please enter a valid UK phone number. |
| `address` | Please enter your address (5 to 300 characters). |
| `message` | Your message must be 2,000 characters or fewer. |
| `appointment_date` | Please pick a valid inspection date. |
| `appointment_date` | Please pick an inspection date from today to 6 days from now. |
| `appointment_time` | Please pick a valid inspection time. |
| `appointment_time` | Please pick a 30-minute inspection slot between 09:00 and 18:00. |
| `appointment_time` | That inspection slot has already started. Please pick another. |
| `images` | You can upload up to 10 photos. |
| `images` | Each photo must be 10MB or smaller. |
| `images` | Photos must be PNG, JPEG, GIF or WEBP images. |

---

## Go live, in this order

1. In Railway, add `DVLA_API_KEY` to the backend service's variables. It is the only DVLA value needed. Check that `ADMIN_EMAIL` is set, because the owner email is skipped without it.
2. Merge and deploy the backend. No migration is needed for the lookup change.
3. Set `NUM_PROXIES` in `REST_FRAMEWORK` to match Railway's proxy chain. Without it, a caller can dodge the rate limits by changing the `X-Forwarded-For` header.
4. Check that `NEXT_PUBLIC_API_URL=https://noorrix-backend-production.up.railway.app` is set on the website's host before building. The page is part of the existing website, so it needs no new CORS entry.
5. Test the lookup on the live site with a real registration.
6. When DVSA approves the registration, add `DVSA_TOKEN_URL`, `DVSA_CLIENT_ID`, `DVSA_CLIENT_SECRET` and `DVSA_API_KEY` in Railway, then test a real registration again. It should now show the model. `DVSA_SCOPE` already has the right default.

### About the DVSA credentials

- Register at https://submit.forms.service.gov.uk/form/2382/register-for-mot-history-api/7519. Approval takes up to 5 working days.
- The DVSA API key is a different key from the DVLA one.
- The DVSA client secret expires every 2 years, and DVSA emails a reminder before then. If it expires, the lookup falls back to DVLA and the model stops showing until the secret is renewed.
- DVSA revokes an API key that is unused for 90 days.

### About the DVLA key

- The key comes from DVLA's Vehicle Enquiry Service. No client ID, secret or token is needed.
- It is free for now. DVLA's terms say it may add charges later, with notice.
- DVLA allows 2 requests per second by default, which is far above this page's rate limits.
- DVLA deletes a key that is unused for 90 days, after emailing a warning.
- DVLA allows one key per company. Requesting more keys can get access revoked, so keep this one.
- Neither DVLA's terms nor DVSA's docs say whether this data may be shown to website visitors. Confirm with them if that matters.

### Owner decisions

- Decide whether inspections and showroom appointments share a calendar. They are separate now, so both could land at the same time.

### Known limits

- The project has no shared cache, so each of the two gunicorn workers keeps its own rate-limit counts and lookup cache. The real limits can be up to 60 lookups and 20 submissions per hour, and counts reset on every deploy. Django's built-in database cache would fix this with no new dependency.
- `SECURE_PROXY_SSL_HEADER` isn't set, so links to photos on the Railway volume in the owner email will probably start with `http://`. Links to Cloudflare R2 aren't affected.
