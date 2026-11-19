import pydantic

from shop.schemas.base import FrozenBaseModel


class Webhook(FrozenBaseModel, extra="ignore"):
    event: str
    delivery_id: str


class WebhookHeaders(FrozenBaseModel):
    model_config = pydantic.ConfigDict(alias_generator=str.lower)

    signature: str
