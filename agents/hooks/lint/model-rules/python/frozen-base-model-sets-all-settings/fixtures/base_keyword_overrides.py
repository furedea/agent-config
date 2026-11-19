import pydantic


class FrozenBaseModel(pydantic.BaseModel, revalidate_instances="never"):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", strict=True, validate_default=True)
