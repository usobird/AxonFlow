"""Managed reusable Skill documents."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from axonflow.api.deps import get_config_dir

router = APIRouter(prefix="/api/skills", tags=["skills"])

_SKILL_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class SkillRequest(BaseModel):
    content: str = Field(max_length=100_000)


def _skills_dir() -> Path:
    return get_config_dir() / "skills"


def _validate_id(skill_id: str) -> None:
    if not _SKILL_ID.fullmatch(skill_id):
        raise HTTPException(status_code=422, detail="Invalid Skill ID")


def _skill_path(skill_id: str) -> Path:
    _validate_id(skill_id)
    return _skills_dir() / skill_id


def _response(skill_id: str, path: Path) -> dict:
    document = path / "SKILL.md" if path.is_dir() else path
    if not document.exists():
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    return {
        "id": skill_id,
        "content": document.read_text(encoding="utf-8"),
        "has_scripts": (path / "scripts").is_dir() if path.is_dir() else False,
    }


@router.get("")
async def list_skills() -> list[dict]:
    directory = _skills_dir()
    if not directory.exists():
        return []
    skills = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_dir() and (path / "SKILL.md").exists():
            skills.append(_response(path.name, path))
        elif path.is_file() and path.suffix == ".md":
            skills.append(_response(path.stem, path))
    return skills


@router.post("/{skill_id}", status_code=201)
async def create_skill(skill_id: str, body: SkillRequest) -> dict:
    path = _skill_path(skill_id)
    if path.exists() or path.with_suffix(".md").exists():
        raise HTTPException(status_code=409, detail=f"Skill already exists: {skill_id}")
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(body.content, encoding="utf-8")
    return _response(skill_id, path)


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict:
    path = _skill_path(skill_id)
    if path.exists():
        return _response(skill_id, path)
    return _response(skill_id, path.with_suffix(".md"))


@router.put("/{skill_id}")
async def update_skill(skill_id: str, body: SkillRequest) -> dict:
    path = _skill_path(skill_id)
    document = path / "SKILL.md" if path.is_dir() else path.with_suffix(".md")
    if not document.exists():
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    document.write_text(body.content, encoding="utf-8")
    return _response(skill_id, path if path.exists() else document)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str) -> None:
    path = _skill_path(skill_id)
    file_path = path.with_suffix(".md")
    if path.is_dir():
        shutil.rmtree(path)
        return
    if file_path.exists():
        file_path.unlink()
        return
    raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
