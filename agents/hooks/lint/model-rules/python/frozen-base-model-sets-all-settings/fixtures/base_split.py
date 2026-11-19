import pydantic


class FrozenBaseModel(pydantic.BaseModel, frozen=True, extra="forbid"):
    model_config = pydantic.ConfigDict(strict=True, validate_default=True, revalidate_instances="always")
