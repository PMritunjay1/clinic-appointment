from typing import Annotated, List, Sequence
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, crud, models
from app.database import get_db
from app.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.DiagnosticCentreResponse, status_code=status.HTTP_201_CREATED)
async def create_centre(
    centre: schemas.DiagnosticCentreCreate, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    if current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return await crud.create_centre(db=db, centre=centre)

@router.get("/", response_model=List[schemas.DiagnosticCentreResponse])
async def read_centres(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0, 
    limit: int = 100
) -> Sequence[models.DiagnosticCentre]:
    return await crud.get_centres(db, skip=skip, limit=limit)

@router.get("/{centre_id}", response_model=schemas.DiagnosticCentreResponse)
async def read_centre(
    centre_id: int, 
    db: Annotated[AsyncSession, Depends(get_db)]
):
    centre = await crud.get_centre(db, centre_id=centre_id)
    if centre is None:
        raise HTTPException(status_code=404, detail="Diagnostic Centre not found")
    return centre

@router.post("/{centre_id}/tests", response_model=schemas.DiagnosticTestResponse, status_code=status.HTTP_201_CREATED)
async def create_test_for_centre(
    centre_id: int, 
    test: schemas.DiagnosticTestCreate, 
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    if current_user.role != models.Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    centre = await crud.get_centre(db, centre_id=centre_id)
    if not centre:
        raise HTTPException(status_code=404, detail="Diagnostic Centre not found")
    return await crud.create_test(db=db, test=test, centre_id=centre_id)
