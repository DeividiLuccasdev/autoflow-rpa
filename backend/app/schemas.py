from datetime import datetime
from decimal import Decimal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer_cnpj: str
    number: str = Field(min_length=1, max_length=30, pattern=r"^\d+$")
    series: str = Field(default="1", min_length=1, max_length=10, pattern=r"^\d+$")
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)

    @field_validator("issuer_cnpj")
    @classmethod
    def validate_cnpj(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9./-]+", value):
            raise ValueError("Use um CNPJ numérico de demonstração")
        digits = re.sub(r"\D", "", value)
        if len(digits) != 14 or len(set(digits)) == 1:
            raise ValueError("CNPJ inválido")
        for length, weights in [(12, [5,4,3,2,9,8,7,6,5,4,3,2]), (13, [6,5,4,3,2,9,8,7,6,5,4,3,2])]:
            remainder = sum(int(n)*w for n, w in zip(digits[:length], weights)) % 11
            if int(digits[length]) != (0 if remainder < 2 else 11-remainder):
                raise ValueError("Dígitos verificadores do CNPJ inválidos")
        return digits

    @field_validator("number", "series")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return str(int(value))

class InvoiceRead(InvoiceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    created_at: datetime

class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event: str
    actor: str
    created_at: datetime

class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    invoice_id: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    dispatch_attempts: int
