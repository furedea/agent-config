import pydantic


class FrozenBaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        frozen=True, extra="ignore", strict=True, validate_default=True, revalidate_instances="always"
    )
