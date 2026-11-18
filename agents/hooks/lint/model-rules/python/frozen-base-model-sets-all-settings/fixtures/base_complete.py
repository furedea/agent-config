"""Base model for schemas that parse untrusted input at a boundary."""

import pydantic


class FrozenBaseModel(pydantic.BaseModel):
    """Freeze a parsed schema and validate it strictly."""

    model_config = pydantic.ConfigDict(
        frozen=True, extra="forbid", strict=True, validate_default=True, revalidate_instances="always"
    )
