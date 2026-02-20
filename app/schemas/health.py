from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    message: str
    version: str = "1.0.0"
