import pydantic
from pydantic.alias_generators import to_camel


class FrozenBaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        frozen=True, extra="forbid", strict=True, validate_default=True, revalidate_instances="always"
    )


class OrderLine(FrozenBaseModel, extra="allow"):
    sku: str
    quantity: int


class Customer(FrozenBaseModel):
    model_config = pydantic.ConfigDict(alias_generator=to_camel, populate_by_name=True)

    customer_id: str
    display_name: str


class ApiSchema(FrozenBaseModel):
    """Base of the public API schemas."""


class OrderDraft(ApiSchema):
    model_config = pydantic.ConfigDict(frozen=False)

    lines: list[OrderLine]


class Event(FrozenBaseModel, strict=True):
    name: str


class Patch(ApiSchema):
    model_config = pydantic.ConfigDict(title="Patch", revalidate_instances="never")

    path: str


class LocalSettings(pydantic.BaseModel, frozen=False, extra="ignore"):
    debug: bool = False
