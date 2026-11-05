# 0013 — Pydantic: make bad data fail at the boundary

Pydantic is the contract layer of an AI application. It validates the three places bad data enters:

- **inbound** — HTTP bodies, webhook payloads, form fields
- **outbound** — the JSON an LLM says it produced
- **configuration** — environment variables and `.env`

`basics.py` runs offline through models, constraints, validators, nested models, JSON Schema, `TypeAdapter`, and typed settings. `structured.py` makes one live **DeepSeek** call and parses the reply into a `Ticket` model.

## Run

```powershell
cd assets\examples\0013-pydantic
uv sync

uv run python basics.py            # no key needed

$env:DEEPSEEK_API_KEY = "sk-..."   # or put it in .env
uv run python structured.py
```

## What `basics.py` prints (real run)

```
== 1. dataclass vs BaseModel =================================
dataclass accepted age='not a number' (str)
pydantic rejected: Input should be a valid integer, unable to parse string as an integer
pydantic coerced "25" -> 25 (int)

== 2. required, optional, defaults ===========================
only required fields: {'name': 'Bob', 'age': 41, 'email': None}
empty name -> loc=('name',) type=string_too_short
bad email -> value is not a valid email address: An email address must have an @-sign.

== 3. constraints and a field validator ======================
{'username': 'alicedev', 'plan': 'team', 'seats': 5}
custom validator -> Value error, username cannot contain spaces

== 4. nested models, lists, serialization ====================
city:      Amsterdam
first:     WIDGET x2
dict:      {'sku': 'GADGET', 'quantity': 1, 'unit_price': 49.99}
pattern -> string_pattern_mismatch

== 5. JSON Schema ============================================
required:   ['order_id', 'customer', 'items']
properties: ['customer', 'items', 'note', 'order_id']
nested:     ['Address', 'Customer', 'LineItem']

== 7. pydantic-settings ======================================
api_key:     **********  (masked)
max_retries: 2
debug:       False
```

If you copy `.env.example` to `.env`, the settings section picks up `DEMO_MAX_RETRIES=3` and `DEMO_DEBUG=true` instead of the defaults.

## What `structured.py` prints (live DeepSeek)

```
ticket schema:
{
  "description": "What we want out of a support message.",
  "properties": {
    "order_id": {"description": "Order id, for example A-1042", "type": "string"},
    "category": {"enum": ["billing", "technical", "other"], "type": "string"},
    "urgency": {"maximum": 5, "minimum": 1, "type": "integer"},
    ...
  },
  "required": ["order_id", "category", "urgency", "wants_refund", "summary"],
  "title": "Ticket",
  "type": "object"
}

type:    Ticket (validated instance)
order:   A-1042
route:   billing
urgency: 5
refund:  True
summary: Order A-1042 was charged twice this month and the customer wants a refund today.

as JSON:
{
  "order_id": "A-1042",
  "category": "billing",
  "urgency": 5,
  "wants_refund": true,
  "summary": "Order A-1042 was charged twice this month and the customer wants a refund today."
}
```

The schema is not decoration: `with_structured_output` hands it to DeepSeek as the function/tool schema, and the reply is validated into `Ticket` before your code sees it.

## The five habits

1. **Put a model at every boundary.** A dict flowing through five functions is untyped; a `Ticket` is checked once and trusted after that.
2. **Use `Field` before a validator.** `ge`, `le`, `min_length`, `pattern` are declarative, appear in the JSON Schema, and are enforced by FastAPI and the model API. Write a validator only for business logic.
3. **Validate cross-field rules with `model_validator`.** `start <= end`, `discount < total`, `refund <= charge` — a single field cannot see the other.
4. **Use `pydantic-settings` for config.** `os.getenv` returns `str | None`; `BaseSettings` returns typed fields and fails at startup, not at the first request. `SecretStr` keeps keys out of logs.
5. **Let the schema be the contract with the model.** Descriptions on fields become instructions to the LLM. A `Literal` is how you make a route impossible to misspell.

## `model_validate` vs `**data`

Both construct a model; `model_validate` takes the dict as one value and supports options such as `strict=True`. Use `**data` in small scripts and `model_validate` at boundaries where the payload is already a dict from an API, queue, or file.

`model_dump()` returns Python objects; `model_dump_json()` returns a JSON string. `model_copy(update={...})` returns a copy with the updates applied — note that Pydantic does not revalidate those updates, so call `model_validate` on the dumped dict if the edit must be checked.

## Files

| file | role |
|---|---|
| `basics.py` | offline tour: models, fields, validators, nesting, schema, settings, strict mode |
| `structured.py` | live DeepSeek extraction into a `Ticket` |
| `common.py` | one `ChatDeepSeek` builder and the missing-key message |
| `.env.example` | copy to `.env` for the key and the settings demo |
| `pyproject.toml` | uv project: pydantic, pydantic-settings, email-validator, langchain, langchain-deepseek |

## If it fails

- **`DEEPSEEK_API_KEY is not set`** — only `structured.py` needs it. Copy the three lines the script prints, or create `.env` from `.env.example`.
- **`ValidationError` on a field you thought was valid** — read `error.errors()`: each item has `loc`, `msg`, and `type`. `loc` is the path, including list indexes and nested models.
- **`EmailStr` import error** — `email-validator` is missing. It is in `pyproject.toml`; run `uv sync`.
- **The model returns the wrong shape** — the provider chose a different tool. Check that `method="function_calling"` is supported by the model, and keep the schema small. Descriptions are part of the prompt.
- **`model_validate` rejects a dict that `Model(**dict)` accepted** — they should agree; if not, you are probably passing a non-dict or using `strict=True` somewhere. Print `type(payload)` first.
