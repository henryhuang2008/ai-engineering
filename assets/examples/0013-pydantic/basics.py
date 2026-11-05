"""Pydantic, from the first model to validated settings - all offline.

Run from this folder:

    uv sync
    uv run python basics.py

No API key is needed. `structured.py` is the live DeepSeek half.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def heading(text: str) -> None:
    print(f"\n== {text} " + "=" * max(0, 58 - len(text)))


# --- 1. a dataclass stores, a model checks ---------------------------------


@dataclass
class DataUser:
    name: str
    age: int


class User(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    age: int = Field(ge=0, le=120)
    email: EmailStr | None = None


heading("1. dataclass vs BaseModel")
raw = DataUser(name="Alice", age="not a number")  # type: ignore[arg-type]
print(f"dataclass accepted age={raw.age!r} ({type(raw.age).__name__})")

try:
    User(name="Alice", age="not a number")
except ValidationError as error:
    print(f"pydantic rejected: {error.errors()[0]['msg']}")

coerced = User(name="Alice", age="25")
print(f'pydantic coerced "25" -> {coerced.age!r} ({type(coerced.age).__name__})')


# --- 2. required, optional, defaults ---------------------------------------


heading("2. required, optional, defaults")
print(f"only required fields: {User(name='Bob', age=41).model_dump()}")
print(f"nullable field:       {User(name='Bob', age=41, email=None).email}")

try:
    User(name="", age=41)
except ValidationError as error:
    detail = error.errors()[0]
    print(f"empty name -> loc={detail['loc']} type={detail['type']}")

try:
    User(name="Bob", age=41, email="not-an-email")
except ValidationError as error:
    print(f"bad email -> {error.errors()[0]['msg']}")


# --- 3. constraints are data, not prose ------------------------------------


class Signup(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    plan: Literal["free", "team", "enterprise"]
    seats: int = Field(default=1, ge=1, le=500)

    @field_validator("username")
    @classmethod
    def no_spaces(cls, value: str) -> str:
        if " " in value:
            raise ValueError("username cannot contain spaces")
        return value.lower()


heading("3. constraints and a field validator")
print(Signup(username="AliceDev", plan="team", seats=5).model_dump())
try:
    Signup(username="Alice Dev", plan="team")
except ValidationError as error:
    print(f"custom validator -> {error.errors()[0]['msg']}")


class DateRange(BaseModel):
    start: int
    end: int

    @model_validator(mode="after")
    def ordered(self) -> "DateRange":
        if self.start > self.end:
            raise ValueError("start must be <= end")
        return self


heading("3b. a model validator sees both fields")
print(DateRange(start=1, end=9).model_dump())
try:
    DateRange(start=9, end=1)
except ValidationError as error:
    print(f"cross-field -> {error.errors()[0]['msg']}")


# --- 4. nested models and lists --------------------------------------------


class Address(BaseModel):
    city: str
    country: str


class Customer(BaseModel):
    name: str
    address: Address


class LineItem(BaseModel):
    sku: str
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)


class Order(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d+$")
    customer: Customer
    items: list[LineItem]
    note: str | None = None


heading("4. nested models, lists, serialization")
payload = {
    "order_id": "ORD-1042",
    "customer": {
        "name": "Dana",
        "address": {"city": "Amsterdam", "country": "NL"},
    },
    "items": [
        {"sku": "WIDGET", "quantity": 2, "unit_price": 29.99},
        {"sku": "GADGET", "quantity": 1, "unit_price": 49.99},
    ],
}
order = Order.model_validate(payload)
print(f"city:      {order.customer.address.city}")
print(f"first:     {order.items[0].sku} x{order.items[0].quantity}")
print(f"dict:      {order.model_dump()['items'][1]}")
print(f"json head: {order.model_dump_json()[:80]}...")

try:
    Order.model_validate({**payload, "order_id": "1042"})
except ValidationError as error:
    print(f"pattern -> {error.errors()[0]['type']}")


# --- 5. JSON Schema: the bridge to tools and LLMs --------------------------


heading("5. JSON Schema")
schema = Order.model_json_schema()
print(f"required:   {schema['required']}")
print(f"properties: {sorted(schema['properties'])}")
print(f"nested:     {sorted(schema['$defs'])}")


# --- 6. TypeAdapter: validate a list without a wrapper model ---------------


heading("6. TypeAdapter for a bare list")
items = TypeAdapter(list[LineItem]).validate_python(
    [{"sku": "WIDGET", "quantity": 2, "unit_price": 29.99}]
)
print(f"{len(items)} item(s), first sku={items[0].sku}")


# --- 7. typed settings: fail at boot, not at request ----------------------


class DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEMO_", env_file=".env", extra="ignore"
    )

    api_key: SecretStr = SecretStr("not-set")
    max_retries: int = Field(default=2, ge=0, le=5)
    debug: bool = False


heading("7. pydantic-settings")
settings = DemoSettings()
print(f"api_key:     {settings.api_key}  (masked)")
print(f"max_retries: {settings.max_retries}")
print(f"debug:       {settings.debug}")
print("values come from DEMO_API_KEY / DEMO_MAX_RETRIES / DEMO_DEBUG or defaults")


# --- 8. strict mode is available, but not the default ----------------------


class StrictUser(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    age: int


heading("8. strict mode")
try:
    StrictUser(name="Alice", age="25")  # type: ignore[arg-type]
except ValidationError as error:
    print(f"strict rejects the string: {error.errors()[0]['msg']}")

print("\ndone: models, fields, validators, nesting, schema, settings.")
