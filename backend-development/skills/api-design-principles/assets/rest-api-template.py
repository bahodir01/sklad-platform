"""
Production-ready REST API template using FastAPI.
Includes pagination, filtering, error handling, and best practices.
"""

from fastapi import FastAPI, HTTPException, Query, Path, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum

app = FastAPI(
    title="API Template",
    version="1.0.0",
    docs_url="/api/docs"
)

# Security Middleware
# Trusted Host: Prevents HTTP Host Header attacks
# Read allowed hosts / origins from the environment so the insecure "*"
# default never silently reaches production. Set ALLOWED_HOSTS and
# ALLOWED_ORIGINS as comma-separated lists (e.g. "api.example.com").
import os

ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h]
ALLOWED_ORIGINS = [o for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o]

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS  # defaults to ["*"] only when ALLOWED_HOSTS is unset
)

# CORS: Configures Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # defaults to ["*"] only when ALLOWED_ORIGINS is unset
    # allow_credentials with a wildcard origin is rejected by browsers, so only
    # enable it when specific origins are configured.
    allow_credentials=ALLOWED_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    status: UserStatus = UserStatus.ACTIVE

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    status: Optional[UserStatus] = None

class User(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Pagination
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int

# Error handling
class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str
    code: str

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[List[ErrorDetail]] = None

def _coerce_details(raw: Any) -> Optional[List[ErrorDetail]]:
    """Normalize a handler-supplied `details` payload into List[ErrorDetail].

    Accepts either a list of dicts/ErrorDetail, or a single dict describing
    one detail, and returns None when nothing usable is provided. This keeps
    the exception handler itself from raising a ValidationError (which would
    otherwise turn a 404 into a 500).
    """
    if raw is None:
        return None
    if isinstance(raw, ErrorDetail):
        return [raw]
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list):
        details: List[ErrorDetail] = []
        for item in raw:
            if isinstance(item, ErrorDetail):
                details.append(item)
            elif isinstance(item, dict):
                details.append(
                    ErrorDetail(
                        field=item.get("field"),
                        message=item.get("message", str(item)),
                        code=item.get("code", "error"),
                    )
                )
        return details or None
    return None


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    if isinstance(exc.detail, str):
        message = exc.detail
        raw_details = None
    elif isinstance(exc.detail, dict):
        message = exc.detail.get("message", "Error")
        raw_details = exc.detail.get("details")
    else:
        message = "Error"
        raw_details = None

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.__class__.__name__,
            message=message,
            details=_coerce_details(raw_details),
        ).model_dump()
    )

# Endpoints
@app.get("/api/users", response_model=PaginatedResponse, tags=["Users"])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[UserStatus] = Query(None),
    search: Optional[str] = Query(None)
):
    """List users with pagination and filtering."""
    # Mock implementation
    total = 100
    items = [
        User(
            id=str(i),
            email=f"user{i}@example.com",
            name=f"User {i}",
            status=UserStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now()
        ).model_dump()
        for i in range((page-1)*page_size, min(page*page_size, total))
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )

@app.post("/api/users", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user(user: UserCreate):
    """Create a new user."""
    # Mock implementation
    return User(
        id="123",
        email=user.email,
        name=user.name,
        status=user.status,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

@app.get("/api/users/{user_id}", response_model=User, tags=["Users"])
async def get_user(user_id: str = Path(..., description="User ID")):
    """Get user by ID."""
    # Mock: Check if exists
    if user_id == "999":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "User not found",
                "details": [
                    {"field": "id", "message": f"No user with id {user_id}", "code": "not_found"}
                ],
            }
        )

    return User(
        id=user_id,
        email="user@example.com",
        name="User Name",
        status=UserStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

@app.patch("/api/users/{user_id}", response_model=User, tags=["Users"])
async def update_user(user_id: str, update: UserUpdate):
    """Partially update user."""
    # Validate user exists
    existing = await get_user(user_id)

    # Apply updates
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(existing, field, value)

    existing.updated_at = datetime.now()
    return existing

@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def delete_user(user_id: str):
    """Delete user."""
    await get_user(user_id)  # Verify exists
    return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
