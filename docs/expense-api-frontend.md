# Car Expense Tracker API — Frontend Integration Guide

Base URL: `https://api.noorrixmotors.co.uk` in production, `http://127.0.0.1:8000` locally.

Front end: the separate Next.js app at `expense.noorrixmotors.co.uk`.

**Status:** the backend is built on branch `feature/expense` and its tests pass. It is not deployed yet, and the front end has not been run against it, so expect some small fixes during step 3 below.

---

## Connect the front end

### 1. Replace the routes

In `src/api.js`, replace `ENDPOINTS` with the block below. Based on reading the front-end code, this is the only code change needed.

```js
const ENDPOINTS = {
  login: "/api/v1/auth/token/",
  cars: "/api/expenses/cars/",
  car: (id) => `/api/expenses/cars/${id}/`,
  summary: "/api/expenses/summary/",
  export: "/api/expenses/export/",
};
```

The trailing slashes are required. Without one, a POST or PUT fails instead of redirecting. Demo mode keeps working, because the mock server reads the same `ENDPOINTS`.

### 2. Run both apps locally

Backend, with `DEBUG=True` in `.env`, which allows all origins:

```bash
python manage.py migrate
python manage.py createsuperuser   # first time only, gives you a staff login
python manage.py runserver 8000
```

Front end, in a new `.env.local` at the project root:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Restart `npm run dev`. The "Demo data" badge disappears once the app is using the real API.

### 3. Check it end to end

You need one staff account and one customer account. Create the customer on the public site or with `POST /api/v1/auth/register/`.

- [ ] A staff account can log in and sees the tracker.
- [ ] A wrong password shows "That email or password is incorrect."
- [ ] A customer account can log in, gets the permission error, and sees no data.
- [ ] Add a car, and it appears first with updated summary cards.
- [ ] Edit a car, and the row and summary update after Save.
- [ ] A value the backend rejects shows its message under the field.
- [ ] All, Available, Sold and search return the right cars.
- [ ] Export downloads a correct CSV that opens in Excel.
- [ ] An invalid or expired token goes to the login page.
- [ ] Reloading the page keeps the saved data.

---

## Login and access

Login is the existing route. There is no separate tracker login.

```
POST /api/v1/auth/token/
{ "email": "staff@example.com", "password": "..." }
```

The response contains `access`, `refresh`, `name` and `email`. Send the access token on every expense request:

```
Authorization: Bearer <access>
```

Access tokens last 60 minutes.

Only accounts with `is_staff` can use the tracker. A staff login is created in Django admin by ticking **Staff status** on the user.

| Caller | Result on every expense endpoint |
|--------|----------------------------------|
| No token, bad token or expired token | `401` |
| Customer account | `403` |
| Staff account | Success |

---

## Endpoints

| Method | Endpoint | Description | Success |
|--------|----------|-------------|---------|
| GET | `/api/expenses/cars/?status=&search=` | List cars | `200` |
| POST | `/api/expenses/cars/` | Add a car | `201` |
| PUT | `/api/expenses/cars/<id>/` | Save a car | `200` |
| GET | `/api/expenses/summary/` | The four summary cards | `200` |
| GET | `/api/expenses/export/?status=&search=` | Download CSV | `200` |

There are no rename or delete endpoints. GET, PATCH and DELETE on `/api/expenses/cars/<id>/` return `405`.

---

## Car JSON

The list, POST and PUT responses all use this shape.

```json
{
  "id": 12,
  "name": "2019 BMW 320d M Sport",
  "status": "available",
  "date_added": "2026-10-06",
  "date_sold": null,
  "purchase": "14300.00",
  "delivery": "220.00",
  "mot": "54.85",
  "wash": "35.00",
  "denting_painting": "420.00",
  "oil_coolant_repairs": "189.99",
  "fuel": "55.00",
  "timing_chain": null,
  "electrical_work": null,
  "brakes": null,
  "exhaust": null,
  "clutch_gearbox": null,
  "other": "95.00",
  "tyre_tread_depth": "4.90",
  "sale_price": "17495.00",
  "notes": "HPI clear. Two keys."
}
```

- Money and tyre depth are strings with two decimal places, or `null` when blank.
- Dates are `yyyy-mm-dd`, or `null` when blank.
- `notes` is always a string, and is `""` when empty.
- Total Cost, Profit and Days in Stock are not in the response. The front end calculates them per row.

| Field | Accepted values |
|-------|-----------------|
| `name` | Required on POST, up to 255 characters |
| `status` | `available` or `sold` |
| `date_added`, `date_sold` | `yyyy-mm-dd` or `null` |
| The 13 cost fields, `sale_price` | `0` to `99999999.99`, up to 2 decimal places, or `null` |
| `tyre_tread_depth` | `0` to `99.99`, up to 2 decimal places, or `null` |
| `notes` | Any string, including `""`. `null` is rejected |

Numbers can be sent as JSON numbers or strings.

---

## `GET /api/expenses/cars/`

Returns a plain JSON array, newest first, with no pagination.

| Param | Behaviour |
|-------|-----------|
| `status` | `available` or `sold`. Absent or empty means all cars. Any other value returns `[]` |
| `search` | Case-insensitive match on `name` or `notes`. Absent or empty means no search |

---

## `POST /api/expenses/cars/`

```json
{ "name": "Ford Fiesta 1.0", "date_added": "2026-11-09", "purchase": 5000.5 }
```

`purchase` and `date_added` can be `null`. New cars are always `available`, and any other field in the body is ignored. Returns `201` with the full car JSON.

---

## `PUT /api/expenses/cars/<id>/`

Send `status`, `date_added`, `date_sold`, `sale_price`, `tyre_tread_depth`, `notes` and the 13 cost fields. Blank numbers and dates are sent as `null`.

Don't send `name`. A missing `name` is fine, and a `name` in the body is ignored, so a car keeps its original name.

Returns `200` with the full car JSON, or `404` if the car doesn't exist.

---

## `GET /api/expenses/summary/`

Takes no filters and always covers every car.

```json
{
  "cars_in_stock": 8,
  "cars_sold": 5,
  "money_tied_up": "86689.24",
  "profit_from_sold": "6273.85"
}
```

| Field | Rule |
|-------|------|
| `cars_in_stock` | Count of `available` cars |
| `cars_sold` | Count of `sold` cars |
| `money_tied_up` | Sum of the 13 costs on `available` cars, counting blanks as 0 |
| `profit_from_sold` | Sum of `sale_price` minus the 13 costs, on `sold` cars that have a `sale_price`. Can be negative |

---

## `GET /api/expenses/export/`

Returns `text/csv; charset=utf-8` and takes the same `status` and `search` filters as the list. The file starts with a UTF-8 byte order mark so Excel reads it correctly.

Columns, in order:

> Car, Status, Date Added, Purchase, Delivery, MOT, Wash, Denting/Painting, Oil Change/Coolant/Repairs, Fuel, Timing Chain, Electrical Work, Brakes, Exhaust, Clutch and Gearbox, Other, Total Cost, Tyre Tread Depth (mm), Sale Price, Profit, Date Sold, Notes

- Status is `Available` or `Sold`.
- Dates are `dd/mm/yyyy`.
- Money is plain, such as `1234.50`, with no £ sign. Blank values are empty cells.
- Total Cost is always filled in, and is `0.00` for a car with no costs.
- Profit is filled in whenever the car has a sale price, including an available car, and is empty otherwise. This matches the Profit column in the tracker table.
- A `name` or `notes` value starting with `=`, `+`, `-` or `@` gets a leading `'`, so spreadsheets don't run it as a formula.

---

## Errors

| Response | Body | What the front end does |
|----------|------|-------------------------|
| `400` | `{ "wash": ["Ensure that there are no more than 2 decimal places."] }` | Shows the message under that field |
| `401` on an expense endpoint | | Clears the token and goes to the login page |
| `401` on login | | Shows "That email or password is incorrect." |
| `403` | `{ "detail": "You do not have permission to perform this action." }` | Shows `detail` on the error screen with a retry button |
| `5xx` | | Shows a generic error with a retry button |

Field error keys are always the API field names above. Example messages:

| Input | Message |
|-------|---------|
| Missing `name` | This field is required. |
| Blank `name` | This field may not be blank. |
| Negative number | Ensure this value is greater than or equal to 0. |
| Too many decimals | Ensure that there are no more than 2 decimal places. |
| Too large | Ensure that there are no more than 8 digits before the decimal point. |
| Not a number | A valid number is required. |
| Bad status | "reserved" is not a valid choice. |
| Bad date | Date has wrong format. Use one of these formats instead: YYYY-MM-DD. |

---

## Notes

- `carFromApi` and `carToApi` in `src/api.js` still mention a `reserved` status. The API only ever returns `available` or `sold`, so that code never runs against real data and can stay.
- The front end sets the download filename itself, so it doesn't need to read the `Content-Disposition` header.
- `POST /api/v1/auth/token/refresh/` already exists. Using it for silent token renewal would be a front-end-only change, so staff wouldn't be sent back to login after 60 minutes.

---

## Go live, in this order

1. Merge `feature/expense` and deploy the backend. Railway's start command runs `migrate`, so the new table is created automatically.
2. Add `https://expense.noorrixmotors.co.uk` to `CORS_ALLOWED_ORIGINS` in Railway, comma-separated from the existing values.
3. In Django admin, tick **Staff status** for each person who should use the tracker.
4. Set `NEXT_PUBLIC_API_URL=https://api.noorrixmotors.co.uk` on the front end's host **before building**. If it is empty, the live site runs on demo data.
5. Deploy the front end, add the custom domain on the host, and add a `CNAME` record named `expense` at the DNS provider.
