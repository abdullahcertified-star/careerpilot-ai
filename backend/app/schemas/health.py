from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check status schema."""

    status: str = Field(default="ok", description="Overall service status")
    app_name: str = Field(description="Name of the running application")
    environment: str = Field(description="Execution environment")
    version: str = Field(default="0.1.0", description="Application version")
