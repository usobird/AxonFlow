"""Reusable model profile APIs."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from axonflow.api.deps import get_platform_store
from axonflow.config.models import ModelConfig

router = APIRouter(prefix="/api/model-profiles", tags=["model-profiles"])


class ModelProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: ModelConfig


@router.get("")
async def list_model_profiles() -> list[dict]:
    return get_platform_store().list_model_profiles()


@router.post("", status_code=201)
async def create_model_profile(body: ModelProfileRequest) -> dict:
    if (
        body.config.credential_id
        and not get_platform_store().get_credential(body.config.credential_id)
    ):
        raise HTTPException(status_code=422, detail="Credential not found")
    try:
        return get_platform_store().create_model_profile(
            body.name,
            body.config.model_dump(mode="json", exclude_none=True),
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{profile_id}", status_code=204)
async def delete_model_profile(profile_id: str) -> None:
    if not get_platform_store().delete_model_profile(profile_id):
        raise HTTPException(status_code=404, detail="Model profile not found")
