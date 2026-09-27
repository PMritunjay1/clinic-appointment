from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from datetime import datetime, timezone
from typing import List, Optional
from app.models import BookingStatus, Role, PaymentStatus

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

class UserResponse(UserBase):
    id: int
    role: Role

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- Test Schemas ---
class DiagnosticTestBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    price: float = Field(..., gt=0, allow_inf_nan=False)

class DiagnosticTestCreate(DiagnosticTestBase):
    pass

class DiagnosticTestResponse(DiagnosticTestBase):
    id: int
    centre_id: int

    model_config = ConfigDict(from_attributes=True)

# --- Centre Schemas ---
class DiagnosticCentreBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    location: str = Field(..., min_length=1, max_length=300)

class DiagnosticCentreCreate(DiagnosticCentreBase):
    pass

class DiagnosticCentreResponse(DiagnosticCentreBase):
    id: int
    tests: List[DiagnosticTestResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

# --- Booking Schemas ---
class BookingBase(BaseModel):
    test_id: int = Field(..., gt=0)
    centre_id: int = Field(..., gt=0)
    appointment_date: datetime

    @field_validator("appointment_date")
    @classmethod
    def appointment_must_be_future(cls, value: datetime) -> datetime:
        now_utc = datetime.now(timezone.utc)
        if value.tzinfo is None:
            if value <= now_utc.replace(tzinfo=None):
                raise ValueError("appointment_date must be in the future")
            return value
        if value <= now_utc:
            raise ValueError("appointment_date must be in the future")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

class BookingCreate(BookingBase):
    pass

class BookingResponse(BookingBase):
    id: int
    user_id: int
    amount: float
    status: BookingStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Payment Schemas ---
class PaymentRequest(BaseModel):
    booking_id: int = Field(..., gt=0)
    card_number: str = Field(
        ..., pattern=r"^[0-9]{12,19}$", description="Dummy card number"
    )
    cvv: str = Field(..., pattern=r"^[0-9]{3,4}$", description="Dummy CVV")

class PaymentResponse(BaseModel):
    booking_id: int
    transaction_id: str
    status: PaymentStatus

class WebhookPayload(BaseModel):
    transaction_id: str = Field(..., min_length=1)
    booking_id: int = Field(..., gt=0)
    status: PaymentStatus
