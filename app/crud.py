from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app import models, schemas
from app.auth import get_password_hash
from typing import Sequence, Optional
from datetime import datetime

# --- Users ---
async def get_user(db: AsyncSession, user_id: int) -> Optional[models.User]:
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    return result.scalars().first()

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[models.User]:
    result = await db.execute(select(models.User).filter(models.User.email == email))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: schemas.UserCreate) -> models.User:
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password, full_name=user.full_name)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

# --- Centres & Tests ---
async def create_centre(db: AsyncSession, centre: schemas.DiagnosticCentreCreate) -> models.DiagnosticCentre:
    db_centre = models.DiagnosticCentre(**centre.model_dump())
    db.add(db_centre)
    await db.commit()
    await db.refresh(db_centre)
    await db.refresh(db_centre, attribute_names=["tests"])
    return db_centre

async def get_centres(db: AsyncSession, skip: int = 0, limit: int = 100) -> Sequence[models.DiagnosticCentre]:
    result = await db.execute(
        select(models.DiagnosticCentre)
        .options(selectinload(models.DiagnosticCentre.tests))
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def get_centre(db: AsyncSession, centre_id: int) -> Optional[models.DiagnosticCentre]:
    result = await db.execute(
        select(models.DiagnosticCentre)
        .options(selectinload(models.DiagnosticCentre.tests))
        .filter(models.DiagnosticCentre.id == centre_id)
    )
    return result.scalars().first()

async def create_test(db: AsyncSession, test: schemas.DiagnosticTestCreate, centre_id: int) -> models.DiagnosticTest:
    db_test = models.DiagnosticTest(**test.model_dump(), centre_id=centre_id)
    db.add(db_test)
    await db.commit()
    await db.refresh(db_test)
    return db_test

async def get_test(db: AsyncSession, test_id: int) -> Optional[models.DiagnosticTest]:
    result = await db.execute(select(models.DiagnosticTest).filter(models.DiagnosticTest.id == test_id))
    return result.scalars().first()

# --- Bookings ---
async def create_booking(db: AsyncSession, booking: schemas.BookingCreate, user_id: int, amount: float) -> models.Booking:
    db_booking = models.Booking(
        **booking.model_dump(),
        user_id=user_id,
        amount=amount
    )
    db.add(db_booking)
    await db.commit()
    await db.refresh(db_booking)
    return db_booking

async def get_booking(db: AsyncSession, booking_id: int) -> Optional[models.Booking]:
    result = await db.execute(select(models.Booking).filter(models.Booking.id == booking_id))
    return result.scalars().first()

async def get_user_bookings(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100) -> Sequence[models.Booking]:
    result = await db.execute(select(models.Booking).filter(models.Booking.user_id == user_id).offset(skip).limit(limit))
    return result.scalars().all()

async def update_booking_status(db: AsyncSession, booking_id: int, status: models.BookingStatus) -> Optional[models.Booking]:
    booking = await get_booking(db, booking_id)
    if booking:
        booking.status = status
        await db.commit()
        await db.refresh(booking)
    return booking

# --- Payments ---
async def create_payment(
    db: AsyncSession, 
    booking_id: int, 
    amount: float, 
    transaction_id: str, 
    status: models.PaymentStatus
) -> models.Payment:
    db_payment = models.Payment(
        booking_id=booking_id,
        amount=amount,
        transaction_id=transaction_id,
        status=status
    )
    db.add(db_payment)
    await db.commit()
    await db.refresh(db_payment)
    return db_payment

async def get_payment_by_transaction_id(db: AsyncSession, transaction_id: str) -> Optional[models.Payment]:
    result = await db.execute(
        select(models.Payment)
        .options(selectinload(models.Payment.booking))
        .filter(models.Payment.transaction_id == transaction_id)
        .with_for_update()
    )
    return result.scalars().first()

async def get_payment_by_booking_id(db: AsyncSession, booking_id: int) -> Optional[models.Payment]:
    result = await db.execute(
        select(models.Payment)
        .options(selectinload(models.Payment.booking))
        .filter(models.Payment.booking_id == booking_id)
    )
    return result.scalars().first()

async def update_payment_status(db: AsyncSession, payment_id: int, status: models.PaymentStatus) -> Optional[models.Payment]:
    result = await db.execute(select(models.Payment).filter(models.Payment.id == payment_id))
    payment = result.scalars().first()
    if payment:
        payment.status = status
        await db.commit()
        await db.refresh(payment)
    return payment
