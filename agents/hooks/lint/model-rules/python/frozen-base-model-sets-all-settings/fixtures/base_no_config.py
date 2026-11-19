import pydantic


class FrozenBaseModel(pydantic.BaseModel, frozen=True):
    """Shared base of the boundary schemas."""
