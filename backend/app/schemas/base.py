from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base class for API schemas, readable directly from ORM objects."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
