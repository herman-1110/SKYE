from fastapi import Header, HTTPException

from config.settings import settings


async def verify_omada_token(authorization: str = Header(..., alias="Authorization")) -> None:
    """FastAPI dependency that validates the Omada Bearer token on /telemetry."""
    if authorization != f"Bearer {settings.OMADA_ACCESS_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")
