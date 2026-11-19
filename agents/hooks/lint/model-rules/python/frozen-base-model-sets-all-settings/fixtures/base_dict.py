from pydantic import BaseModel


class FrozenBaseModel(BaseModel):
    model_config = {
        "frozen": True,
        "extra": "forbid",
        "strict": True,
        "validate_default": True,
        "revalidate_instances": "always",
    }
