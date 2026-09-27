import pytest
from datetime import datetime
from httpx import AsyncClient
from main import app
from app.database import Base, get_db
from app import models
from app.auth import create_access_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

async def seed_user(email: str, role: models.Role = models.Role.USER) -> None:
    async with TestingSessionLocal() as session:
        session.add(
            models.User(
                email=email,
                hashed_password="unused-test-hash",
                role=role,
            )
        )
        await session.commit()

def auth_headers(email: str) -> dict[str, str]:
    token = create_access_token(data={"sub": email})
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_read_main(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()

@pytest.mark.asyncio
async def test_signup(async_client: AsyncClient):
    response = await async_client.post(
        "/api/auth/signup",
        json={"email": "testuser@example.com", "password": "password123", "full_name": "Test User"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert "id" in data

@pytest.mark.asyncio
async def test_signup_validation_and_login(async_client: AsyncClient):
    invalid_email = await async_client.post(
        "/api/auth/signup",
        json={"email": "not-an-email", "password": "password123"},
    )
    short_password = await async_client.post(
        "/api/auth/signup",
        json={"email": "short-password@example.com", "password": "short"},
    )
    assert invalid_email.status_code == 422
    assert short_password.status_code == 422

    signup = await async_client.post(
        "/api/auth/signup",
        json={"email": "login-user@example.com", "password": "password123"},
    )
    assert signup.status_code == 201
    login = await async_client.post(
        "/api/auth/login",
        data={"username": "login-user@example.com", "password": "password123"},
    )
    bad_login = await async_client.post(
        "/api/auth/login",
        data={"username": "login-user@example.com", "password": "incorrect"},
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    assert login.json()["access_token"]
    assert bad_login.status_code == 401
    assert (await async_client.get("/api/bookings/")).status_code == 401

@pytest.mark.asyncio
async def test_centre_and_test_admin_permissions(async_client: AsyncClient):
    await seed_user("regular-centre-user@example.com")
    await seed_user("admin-centre-user@example.com", role=models.Role.ADMIN)
    user_headers = auth_headers("regular-centre-user@example.com")
    admin_headers = auth_headers("admin-centre-user@example.com")

    denied = await async_client.post(
        "/api/centres/",
        json={"name": "Denied Centre", "location": "Test City"},
        headers=user_headers,
    )
    assert denied.status_code == 403

    created = await async_client.post(
        "/api/centres/",
        json={"name": "Central Diagnostics", "location": "Test City"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    centre_id = created.json()["id"]

    denied_test = await async_client.post(
        f"/api/centres/{centre_id}/tests",
        json={"name": "Blood Panel", "price": 45.5},
        headers=user_headers,
    )
    assert denied_test.status_code == 403

    created_test = await async_client.post(
        f"/api/centres/{centre_id}/tests",
        json={"name": "Blood Panel", "price": 45.5},
        headers=admin_headers,
    )
    assert created_test.status_code == 201
    invalid_test = await async_client.post(
        f"/api/centres/{centre_id}/tests",
        json={"name": "Invalid Panel", "price": -1},
        headers=admin_headers,
    )
    assert invalid_test.status_code == 422

    listed = await async_client.get("/api/centres/")
    assert listed.status_code == 200
    assert listed.json()[0]["tests"][0]["price"] == 45.5

@pytest.mark.asyncio
async def test_booking_validation_and_owner_access(async_client: AsyncClient):
    await seed_user("booking-owner@example.com")
    await seed_user("booking-other@example.com")
    async with TestingSessionLocal() as session:
        centre = models.DiagnosticCentre(name="Booking Centre", location="Test City")
        other_centre = models.DiagnosticCentre(name="Other Centre", location="Other City")
        session.add_all([centre, other_centre])
        await session.flush()
        test = models.DiagnosticTest(name="MRI", price=125.75, centre_id=centre.id)
        session.add(test)
        await session.commit()
        centre_id = centre.id
        other_centre_id = other_centre.id
        test_id = test.id

    owner_headers = auth_headers("booking-owner@example.com")
    other_headers = auth_headers("booking-other@example.com")
    booking_payload = {
        "test_id": test_id,
        "centre_id": centre_id,
        "appointment_date": "2030-01-01T10:00:00",
    }
    created = await async_client.post(
        "/api/bookings/", json=booking_payload, headers=owner_headers
    )
    assert created.status_code == 201
    assert created.json()["amount"] == 125.75
    booking_id = created.json()["id"]

    mismatch = await async_client.post(
        "/api/bookings/",
        json={**booking_payload, "centre_id": other_centre_id},
        headers=owner_headers,
    )
    past_appointment = await async_client.post(
        "/api/bookings/",
        json={**booking_payload, "appointment_date": "2020-01-01T10:00:00"},
        headers=owner_headers,
    )
    missing_centre = await async_client.post(
        "/api/bookings/",
        json={**booking_payload, "centre_id": 9999},
        headers=owner_headers,
    )
    assert mismatch.status_code == 400
    assert past_appointment.status_code == 422
    assert missing_centre.status_code == 404

    own_booking = await async_client.get(
        f"/api/bookings/{booking_id}", headers=owner_headers
    )
    other_booking = await async_client.get(
        f"/api/bookings/{booking_id}", headers=other_headers
    )
    missing_booking = await async_client.get(
        "/api/bookings/9999", headers=owner_headers
    )
    owner_bookings = await async_client.get("/api/bookings/", headers=owner_headers)
    assert own_booking.status_code == 200
    assert other_booking.status_code == 403
    assert missing_booking.status_code == 404
    assert [item["id"] for item in owner_bookings.json()] == [booking_id]

@pytest.mark.asyncio
async def test_payment_rejects_missing_and_foreign_bookings(async_client: AsyncClient):
    await seed_user("payment-owner@example.com")
    await seed_user("payment-stranger@example.com")
    async with TestingSessionLocal() as session:
        centre = models.DiagnosticCentre(name="Payment Centre", location="Test City")
        session.add(centre)
        await session.flush()
        test = models.DiagnosticTest(name="X-Ray", price=25, centre_id=centre.id)
        session.add(test)
        await session.flush()
        owner = await session.scalar(
            select(models.User).where(models.User.email == "payment-owner@example.com")
        )
        assert owner is not None
        booking = models.Booking(
            user_id=owner.id,
            test_id=test.id,
            centre_id=centre.id,
            appointment_date=datetime(2030, 1, 1),
            amount=25,
            status=models.BookingStatus.PENDING,
        )
        session.add(booking)
        await session.commit()
        booking_id = booking.id

    payment_payload = {
        "booking_id": booking_id,
        "card_number": "4111111111111111",
        "cvv": "123",
    }
    foreign_payment = await async_client.post(
        "/api/payments/",
        json=payment_payload,
        headers=auth_headers("payment-stranger@example.com"),
    )
    missing_payment = await async_client.post(
        "/api/payments/",
        json={**payment_payload, "booking_id": 9999},
        headers=auth_headers("payment-owner@example.com"),
    )
    invalid_card = await async_client.post(
        "/api/payments/",
        json={**payment_payload, "cvv": "x"},
        headers=auth_headers("payment-owner@example.com"),
    )
    assert foreign_payment.status_code == 403
    assert missing_payment.status_code == 404
    assert invalid_card.status_code == 422

@pytest.mark.parametrize(
    ("card_number", "expected_payment_status", "expected_booking_status"),
    [
        ("4111111111111111", "SUCCESS", models.BookingStatus.CONFIRMED),
        ("0000000000000000", "FAILED", models.BookingStatus.FAILED),
    ],
)
@pytest.mark.asyncio
async def test_simulated_payment_updates_booking_status(
    async_client: AsyncClient,
    card_number: str,
    expected_payment_status: str,
    expected_booking_status: models.BookingStatus,
):
    async with TestingSessionLocal() as session:
        centre = models.DiagnosticCentre(name="Payment Centre", location="Test City")
        user = models.User(
            email="payment-user@example.com",
            hashed_password="not-used",
        )
        session.add_all([centre, user])
        await session.flush()

        test = models.DiagnosticTest(
            name="Blood Test",
            price=50,
            centre_id=centre.id,
        )
        session.add(test)
        await session.flush()

        booking = models.Booking(
            user_id=user.id,
            test_id=test.id,
            centre_id=centre.id,
            appointment_date=datetime(2030, 1, 1),
            amount=50,
            status=models.BookingStatus.PENDING,
        )
        session.add(booking)
        await session.commit()
        booking_id = booking.id

    token = create_access_token(data={"sub": "payment-user@example.com"})
    response = await async_client.post(
        "/api/payments/",
        json={
            "booking_id": booking_id,
            "card_number": card_number,
            "cvv": "123",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == expected_payment_status
    async with TestingSessionLocal() as session:
        booking = await session.get(models.Booking, booking_id)
        assert booking is not None
        assert booking.status == expected_booking_status

@pytest.mark.parametrize(
    ("webhook_booking", "webhook_status"),
    [("other", "SUCCESS"), ("correct", "PENDING")],
)
@pytest.mark.asyncio
async def test_webhook_validation_and_idempotent_replay(
    async_client: AsyncClient,
    webhook_booking: str,
    webhook_status: str,
):
    async with TestingSessionLocal() as session:
        centre = models.DiagnosticCentre(name="Test Centre", location="Test City")
        user = models.User(
            email="webhook-user@example.com",
            hashed_password="not-used",
        )
        session.add_all([centre, user])
        await session.flush()

        test = models.DiagnosticTest(
            name="Blood Test",
            price=50,
            centre_id=centre.id,
        )
        session.add(test)
        await session.flush()

        correct_booking = models.Booking(
            user_id=user.id,
            test_id=test.id,
            centre_id=centre.id,
            appointment_date=datetime(2030, 1, 1),
            amount=50,
            status=models.BookingStatus.PENDING,
        )
        other_booking = models.Booking(
            user_id=user.id,
            test_id=test.id,
            centre_id=centre.id,
            appointment_date=datetime(2030, 1, 2),
            amount=50,
            status=models.BookingStatus.PENDING,
        )
        session.add_all([correct_booking, other_booking])
        await session.flush()
        payment = models.Payment(
            booking_id=correct_booking.id,
            amount=50,
            transaction_id="txn_webhook_mismatch",
            status=models.PaymentStatus.PENDING,
        )
        session.add(payment)
        await session.commit()
        correct_booking_id = correct_booking.id
        other_booking_id = other_booking.id
        payment_id = payment.id

    response = await async_client.post(
        "/api/payments/webhook/",
        json={
            "transaction_id": "txn_webhook_mismatch",
            "booking_id": other_booking_id if webhook_booking == "other" else correct_booking_id,
            "status": webhook_status,
        },
    )

    assert response.status_code == 400
    async with TestingSessionLocal() as session:
        correct_booking = await session.get(models.Booking, correct_booking_id)
        other_booking = await session.get(models.Booking, other_booking_id)
        payment = await session.get(models.Payment, payment_id)
        assert correct_booking is not None
        assert other_booking is not None
        assert payment is not None
        assert correct_booking.status == models.BookingStatus.PENDING
        assert other_booking.status == models.BookingStatus.PENDING
        assert payment.status == models.PaymentStatus.PENDING

    valid_payload = {
        "transaction_id": "txn_webhook_mismatch",
        "booking_id": correct_booking_id,
        "status": "SUCCESS",
    }
    first_replay = await async_client.post("/api/payments/webhook/", json=valid_payload)
    second_replay = await async_client.post("/api/payments/webhook/", json=valid_payload)
    assert first_replay.status_code == 200
    assert second_replay.status_code == 200
    assert second_replay.json()["message"] == "Already processed"

    conflicting_event = await async_client.post(
        "/api/payments/webhook/",
        json={**valid_payload, "status": "FAILED"},
    )
    assert conflicting_event.status_code == 409

    async with TestingSessionLocal() as session:
        booking = await session.get(models.Booking, correct_booking_id)
        payments = (
            await session.execute(
                select(models.Payment).where(models.Payment.booking_id == correct_booking_id)
            )
        ).scalars().all()
        assert booking is not None
        assert booking.status == models.BookingStatus.CONFIRMED
        assert len(payments) == 1
        assert payments[0].status == models.PaymentStatus.SUCCESS
