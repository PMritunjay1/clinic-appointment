# EVE Healthcare Backend Assignment

This is a backend service for diagnostic test bookings and simulated payments, built using **FastAPI** and **PostgreSQL**.

# EVE Healthcare API

FastAPI service for diagnostic-centre discovery, test bookings, and simulated payments. The application uses async SQLAlchemy and supports PostgreSQL or SQLite. Swagger UI is available at `/docs` while the service is running.

## Run Locally

Requirements: Python 3.11+ and pip. SQLite is used by default, so PostgreSQL is optional for local development.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

On macOS/Linux, activate with `source .venv/bin/activate`. The API is served at `http://localhost:8000`; interactive documentation is at `http://localhost:8000/docs`.

To use PostgreSQL, set `DATABASE_URL` to an async SQLAlchemy URL, for example `postgresql+asyncpg://user:password@localhost:5432/eve_db`. Set `SECRET_KEY` to a private random value outside local development. The fallback signing key and credentials in `docker-compose.yml` are for local demonstration only.

## Run with Docker

Docker Compose starts PostgreSQL and the API:

```bash
docker compose up --build
```

The API is available at `http://localhost:8000`. The Compose file includes demo database credentials and a demo JWT key; replace them before any shared or deployed use.

## Tests

```bash
python -m pytest -q
```

Tests use an isolated in-memory SQLite database and cover signup/login validation, admin inventory permissions, booking ownership and centre/test validation, payment outcomes and authorization, webhook association checks, invalid statuses, replay idempotency, and conflicting final statuses.

## Data Model

- `User` stores a unique email, password hash, optional full name, and `USER`/`ADMIN` role.
- `DiagnosticCentre` has a one-to-many relationship with `DiagnosticTest`.
- `Booking` references its user, test, and centre. Its `amount` is copied from the test price at booking time so later price changes do not alter the booking amount. Booking states are `PENDING`, `CONFIRMED`, `FAILED`, and `CANCELLED`.
- `Payment` has a unique one-to-one relationship with a booking and a unique transaction ID. Payment states are `PENDING`, `SUCCESS`, and `FAILED`.

Foreign keys and unique constraints protect the core relationships. The API also checks that a booked test belongs to the selected centre. Tables are created from SQLAlchemy metadata at startup; migration scripts are not yet configured.

## API

All application routes are under `/api`. Signup and login are public. Centre/test reads are public; creating centres and tests requires an `ADMIN` token. Booking and payment operations require a bearer token. A user can only read or pay for their own booking (admins may read any booking).

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/signup` | Public | Create a user |
| `POST` | `/api/auth/login` | Public | Get a JWT using form fields `username` (email) and `password` |
| `GET` | `/api/centres/` | Public | List centres and offered tests; supports `skip` and `limit` |
| `GET` | `/api/centres/{centre_id}` | Public | Get one centre and its tests |
| `POST` | `/api/centres/` | Admin | Create a centre |
| `POST` | `/api/centres/{centre_id}/tests` | Admin | Add a test and price to a centre |
| `POST` | `/api/bookings/` | User | Book a test |
| `GET` | `/api/bookings/` | User | List the current user's bookings |
| `GET` | `/api/bookings/{booking_id}` | Owner/Admin | Get a booking |
| `POST` | `/api/payments/` | Booking owner | Simulate payment and update booking status |
| `POST` | `/api/payments/webhook/` | Simulated provider | Apply a final payment status idempotently |

### Example Requests

Create an account and obtain a token:

```bash
curl -X POST http://localhost:8000/api/auth/signup \
   -H 'Content-Type: application/json' \
   -d '{"email":"patient@example.com","password":"correct-horse-1","full_name":"Example Patient"}'

curl -X POST http://localhost:8000/api/auth/login \
   -H 'Content-Type: application/x-www-form-urlencoded' \
   -d 'username=patient@example.com&password=correct-horse-1'
```

Use the returned `access_token` as `$TOKEN`. After an administrator has created a centre and test, create a booking:

```bash
curl -X POST http://localhost:8000/api/bookings/ \
   -H "Authorization: Bearer $TOKEN" \
   -H 'Content-Type: application/json' \
   -d '{"test_id":1,"centre_id":1,"appointment_date":"2030-01-01T10:00:00"}'
```

Simulated payment succeeds for any valid 12-19 digit number other than sixteen zeroes. `0000000000000000` simulates a decline. This is test behavior only; card data is not sent to or stored by a real payment provider.

```bash
curl -X POST http://localhost:8000/api/payments/ \
   -H "Authorization: Bearer $TOKEN" \
   -H 'Content-Type: application/json' \
   -d '{"booking_id":1,"card_number":"4111111111111111","cvv":"123"}'
```

The response includes `transaction_id` and final payment `status`. A simulated provider can send the same final status to the webhook repeatedly; an identical replay is acknowledged without duplicate records or state changes. A conflicting final status for that transaction is rejected with `409`.

```bash
curl -X POST http://localhost:8000/api/payments/webhook/ \
   -H 'Content-Type: application/json' \
   -d '{"transaction_id":"txn_from_payment_response","booking_id":1,"status":"SUCCESS"}'
```

## Assumptions and Security

- Admin accounts are provisioned out of band by a trusted operator; public signup always creates a normal user.
- The payment endpoint is deterministic simulation, not a real card processor. Any syntactically valid test card except the decline number succeeds.
- Appointment times must be in the future. Timezone-aware values are converted to UTC; timezone-naive values are interpreted as UTC.
- The webhook is intentionally unauthenticated for this assignment. A deployed integration must verify provider signatures, use unique provider event IDs, and monitor/retry failed processing.
- Webhook state changes lock the matching payment row on databases that support row-level locking. Conflicting terminal status updates are rejected.
- Startup `create_all` is convenient for this exercise; production schema changes should use versioned migrations.

## Further Improvements

- Add Alembic migration scripts and a controlled admin-provisioning command.
- Use provider signatures and event IDs for webhook authentication and durable event deduplication.
- Expand concurrency tests against PostgreSQL, and add rate limiting, structured request correlation, and operational metrics.
- Consider decimal database types for monetary values and add explicit appointment cancellation/rescheduling workflows.
