import uuid
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, crud, models
from app.database import get_db
from app.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=schemas.PaymentResponse)
async def initiate_payment(
    payment_request: schemas.PaymentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """
    Simulated payment endpoint.
    Do not integrate a real payment gateway. Create a mock payment endpoint that simulates payment processing.
    """
    booking = await crud.get_booking(db, booking_id=payment_request.booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    if booking.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to pay for this booking")

    if booking.status == models.BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Booking is already confirmed")
    if booking.status == models.BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Cannot pay for a cancelled booking")

    # Simulate payment processing logic
    is_success = payment_request.card_number != "0000000000000000"
    
    transaction_id = f"txn_{uuid.uuid4().hex}"
    payment_status = models.PaymentStatus.SUCCESS if is_success else models.PaymentStatus.FAILED
    
    # Create or update payment record
    existing_payment = await crud.get_payment_by_booking_id(db, booking_id=booking.id)
    if existing_payment:
        existing_payment.transaction_id = transaction_id
        existing_payment.status = payment_status
    else:
        db.add(
            models.Payment(
                booking_id=booking.id,
                amount=booking.amount,
                transaction_id=transaction_id,
                status=payment_status,
            )
        )

    booking.status = (
        models.BookingStatus.CONFIRMED if is_success else models.BookingStatus.FAILED
    )
    await db.commit()

    return schemas.PaymentResponse(
        booking_id=booking.id,
        transaction_id=transaction_id,
        status=payment_status
    )

@router.post("/webhook/")
async def payment_webhook(
    payload: schemas.WebhookPayload,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Webhook endpoint that accepts payment-status updates from a simulated payment provider.
    Important: The webhook must be idempotent.
    """
    logger.info("Received webhook for booking %s, transaction %s", payload.booking_id, payload.transaction_id)
    
    payment = await crud.get_payment_by_transaction_id(db, transaction_id=payload.transaction_id)
    if not payment:
        logger.error("Transaction %s not found.", payload.transaction_id)
        raise HTTPException(status_code=404, detail="Transaction not found")

    if payment.booking_id != payload.booking_id:
        raise HTTPException(status_code=400, detail="Transaction does not belong to this booking")

    if payload.status == models.PaymentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Webhook status must be final")

    if (
        payment.status in (models.PaymentStatus.SUCCESS, models.PaymentStatus.FAILED)
        and payment.status != payload.status
    ):
        raise HTTPException(status_code=409, detail="Payment already has a conflicting final status")

    new_booking_status = (
        models.BookingStatus.CONFIRMED
        if payload.status == models.PaymentStatus.SUCCESS
        else models.BookingStatus.FAILED
    )

    # Idempotency check
    if (
        payment.status == payload.status 
        and payment.booking is not None
        and payment.booking.status == new_booking_status
    ):
        logger.info("Webhook event already processed. Returning 200.")
        return {"status": "ok", "message": "Already processed"}

    # Update payment status
    payment.status = payload.status
    payment.booking.status = new_booking_status
    await db.commit()
    
    logger.info("Successfully processed webhook. Booking %s status updated to %s.", payload.booking_id, new_booking_status)

    return {"status": "ok"}
