from typing import Annotated, List, Sequence
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, crud, models
from app.database import get_db
from app.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    booking: schemas.BookingCreate, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    centre = await crud.get_centre(db, centre_id=booking.centre_id)
    if not centre:
        raise HTTPException(status_code=404, detail="Diagnostic Centre not found")
    
    test = await crud.get_test(db, test_id=booking.test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Diagnostic Test not found")
    
    if test.centre_id != centre.id:
        raise HTTPException(status_code=400, detail="Test is not available at this centre")

    return await crud.create_booking(
        db=db, 
        booking=booking, 
        user_id=current_user.id, 
        amount=test.price
    )

@router.get("/", response_model=List[schemas.BookingResponse])
async def read_user_bookings(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
    skip: int = 0, 
    limit: int = 100
) -> Sequence[models.Booking]:
    return await crud.get_user_bookings(
        db, 
        user_id=current_user.id, 
        skip=skip, 
        limit=limit
    )

@router.get("/{booking_id}", response_model=schemas.BookingResponse)
async def read_booking(
    booking_id: int, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    booking = await crud.get_booking(db, booking_id=booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != current_user.id and current_user.role != models.Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized to access this booking"
        )
    return booking
