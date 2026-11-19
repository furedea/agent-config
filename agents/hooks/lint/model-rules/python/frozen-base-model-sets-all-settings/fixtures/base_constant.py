import pydantic

LOCKED_SETTINGS = pydantic.ConfigDict(
    frozen=True,
    extra="forbid",
    strict=True,
    validate_default=True,
    revalidate_instances="always",
)


class FrozenBaseModel(pydantic.BaseModel):
    model_config = LOCKED_SETTINGS
