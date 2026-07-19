from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import cast

from cryptography.fernet import Fernet
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from reaper.engine.models.resources import (
    SessionLocal,
    VaultEntry,
    VaultSettings,
)
from reaper.security.vault_crypto import (
    derive_fernet_key,
    generate_salt,
    hash_passcode,
    verify_passcode,
)
from reaper.services.credential_service import get_credential_service
from reaper.utils.error_handler import get_logger
from reaper.web.app_async import VAULT_UNLOCK_TTL_SEC


def jsonify(*args, **kwargs):
    from fastapi.responses import JSONResponse
    content = args[0] if args and isinstance(args[0], dict) else kwargs
    status_code = kwargs.pop("status_code", 200)
    return JSONResponse(content=content, status_code=status_code)

logger = get_logger(__name__)

router = APIRouter(tags=["vault"])

@router.get("/api/vault/status")
async def vault_status(request: Request):
    configured = await asyncio.to_thread(_vault_settings_row) is not None
    return jsonify(
        {
            "status": "success",
            "configured": configured,
            "unlocked": _is_vault_unlocked(request),
        }
    )

@router.post("/api/vault/setup")
async def vault_setup(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not data:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Request body is required."}
        )

    passcode = (data.get("passcode") or "").strip()
    confirm = (data.get("confirm") or "").strip()
    passcode_type = (data.get("passcode_type") or "password").strip().lower()

    if passcode_type == "pin":
        if len(passcode) != 4:
            return jsonify(
                {"status": "error", "message": "PIN passcode must be exactly 4 digits/characters."},
                status_code=400,
            )
    elif len(passcode) < 8:
        return jsonify(
            {"status": "error", "message": "Password passcode must be at least 8 characters."},
            status_code=400,
        )

    if passcode != confirm:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Passcodes do not match."}
        )

    def _create_vault():
        db = SessionLocal()
        try:
            if db.query(VaultSettings).first():
                return "already_configured", None
            salt = generate_salt()
            vs = VaultSettings(
                salt=base64.b64encode(salt).decode("utf-8"),
                passcode_verifier=hash_passcode(passcode, salt),
            )
            db.add(vs)
            db.commit()
            db.refresh(vs)
            return "ok", vs
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        status, vault_settings = await asyncio.to_thread(_create_vault)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    if status == "already_configured":
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Vault is already configured."},
        )

    _unlock_vault_session(request, passcode, vault_settings)
    return {"status": "success", "message": "Vault created and unlocked."}

@router.post("/api/vault/reset")
async def vault_reset(request: Request):
    """Erases all stored vault entries and resets the passcode setup status."""
    def _do_reset():
        db = SessionLocal()
        try:
            db.query(VaultEntry).delete()
            db.query(VaultSettings).delete()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        await asyncio.to_thread(_do_reset)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    request.session.pop("vault_unlocked", None)
    request.session.pop("vault_unlock_expires", None)
    request.session.pop("vault_fernet_key", None)

    return jsonify(
        {"status": "success", "message": "Vault successfully reset. All stored secrets erased."}
    )

@router.post("/api/vault/unlock")
async def vault_unlock(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    if not data:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Request body is required."}
        )

    passcode = (data.get("passcode") or "").strip()
    if not passcode:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Passcode is required."}
        )

    settings = await asyncio.to_thread(_vault_settings_row)
    if not settings:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Vault is not configured yet."}
        )
    if not _unlock_vault_session(request, passcode, settings):
        return JSONResponse(
            status_code=401, content={"status": "error", "message": "Incorrect passcode."}
        )
    return {"status": "success", "message": "Vault unlocked."}

@router.post("/api/vault/lock")
async def vault_lock(request: Request):
    request.session.pop("vault_unlocked", None)
    request.session.pop("vault_unlock_expires", None)
    request.session.pop("vault_fernet_key", None)
    return {"status": "success", "message": "Vault locked."}

@router.get("/api/vault/entries")
async def vault_list_entries(request: Request):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

    def _list_entries():
        db = SessionLocal()
        try:
            rows = db.query(VaultEntry).order_by(VaultEntry.updated_at.desc()).all()
            return [
                {
                    "id": row.id,
                    "label": row.label,
                    "entry_type": row.entry_type,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ]
        finally:
            db.close()

    try:
        entries = await asyncio.to_thread(_list_entries)
        return {"status": "success", "entries": entries}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.post("/api/vault/entries")
async def vault_create_entry(request: Request):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

    fernet = _session_fernet(request)
    if not fernet:
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault session expired."}
        )

    try:
        data = await request.json()
    except Exception:
        data = {}
    if not data:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Request body is required."}
        )

    label = (data.get("label") or "").strip()
    entry_type = (data.get("entry_type") or "credential").strip().lower()
    value = (data.get("value") or "").strip()
    username = (data.get("username") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not label or not value:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Label and secret value are required."},
        )
    if entry_type not in {"credential", "passcode", "note"}:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Invalid entry type."}
        )

    payload = {"value": value, "username": username, "notes": notes}
    try:
        token = fernet.encrypt(json.dumps(payload).encode("utf-8")).decode("utf-8")
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"status": "error", "message": f"Encryption failed: {e!s}"}
        )

    def _save_entry():
        db = SessionLocal()
        try:
            e = VaultEntry(label=label, entry_type=entry_type, encrypted_payload=token)
            db.add(e)
            db.commit()
            db.refresh(e)
            return {"id": e.id, "label": e.label, "entry_type": e.entry_type}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        saved = await asyncio.to_thread(_save_entry)
        return jsonify(
            {
                "status": "success",
                "message": "Entry saved.",
                "entry": saved,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@router.get("/api/vault/entries/{entry_id}")
async def vault_get_entry(request: Request, entry_id: int):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

    fernet = _session_fernet(request)
    if not fernet:
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault session expired."}
        )

    def _fetch_entry():
        db = SessionLocal()
        try:
            row = db.query(VaultEntry).filter_by(id=entry_id).first()
            if not row:
                return None
            return row.encrypted_payload, row.id, row.label, row.entry_type
        finally:
            db.close()

    try:
        result = await asyncio.to_thread(_fetch_entry)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    if result is None:
        return JSONResponse(
            status_code=404, content={"status": "error", "message": "Entry not found."}
        )

    encrypted_payload, row_id, row_label, row_entry_type = result
    try:
        payload = json.loads(fernet.decrypt(encrypted_payload.encode("utf-8")).decode("utf-8"))
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Unable to decrypt entry: {e!s}"},
        )

    return jsonify(
        {
            "status": "success",
            "entry": {
                "id": row_id,
                "label": row_label,
                "entry_type": row_entry_type,
                "username": payload.get("username", ""),
                "value": payload.get("value", ""),
                "notes": payload.get("notes", ""),
            },
        }
    )

@router.delete("/api/vault/entries/{entry_id}")
async def vault_delete_entry(request: Request, entry_id: int):
    if not _is_vault_unlocked(request):
        return JSONResponse(
            status_code=403, content={"status": "error", "message": "Vault is locked."}
        )

    def _delete_entry():
        db = SessionLocal()
        try:
            row = db.query(VaultEntry).filter_by(id=entry_id).first()
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        found = await asyncio.to_thread(_delete_entry)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    if not found:
        return JSONResponse(
            status_code=404, content={"status": "error", "message": "Entry not found."}
        )
    return {"status": "success", "message": "Entry deleted."}

def _vault_settings_row() -> VaultSettings | None:
    """Synchronous helper — callers must wrap in asyncio.to_thread from async context."""
    db = SessionLocal()
    try:
        return db.query(VaultSettings).first()
    except Exception as e:
        print(f"[!] Error fetching vault settings: {e}")
        return None
    finally:
        db.close()

def _vault_salt_bytes(settings: VaultSettings) -> bytes:
    return base64.b64decode(settings.salt.encode("utf-8"))

def _is_vault_unlocked(request: Request) -> bool:
    if not request.session.get("vault_unlocked"):
        return False
    expires = request.session.get("vault_unlock_expires", 0)
    if time.time() > float(expires):
        request.session.pop("vault_unlocked", None)
        request.session.pop("vault_unlock_expires", None)
        request.session.pop("vault_fernet_key", None)
        return False
    return bool(request.session.get("vault_fernet_key"))

def _session_fernet(request: Request) -> Fernet | None:
    key = request.session.get("vault_fernet_key")
    if not key or not _is_vault_unlocked(request):
        return None
    return Fernet(key.encode("utf-8"))

def _unlock_vault_session(request: Request, passcode: str, settings: VaultSettings) -> bool:
    salt = _vault_salt_bytes(settings)
    if not verify_passcode(passcode, salt, cast(str, settings.passcode_verifier)):
        return False
    request.session["vault_fernet_key"] = derive_fernet_key(passcode, salt).decode("utf-8")
    request.session["vault_unlocked"] = True
    request.session["vault_unlock_expires"] = time.time() + VAULT_UNLOCK_TTL_SEC
    return True


# ─── Frontend Alias Routes ─────────────────────────────────────────────────────

@router.post("/api/vault/config")
async def vault_config_alias(request: Request):
    """Alias: '/api/vault/config' → canonical '/api/vault/setup'.
    Used by performance-utils.js to persist vault configuration.
    The payload shape is identical to the setup endpoint.
    """
    from reaper.web.routers.vault import setup_vault
    return await setup_vault(request)
