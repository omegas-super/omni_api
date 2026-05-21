from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile

from app.services.voice_ai import process_voice_turn
from app.state import store, utc_now

router = APIRouter(prefix="/v1/voice", tags=["voice"])


@router.post("/sessions")
def create_voice_session(siteId: str = Form("main_site"), machineId: str | None = Form(None)):
    session_id = str(uuid4())
    store.voice_sessions[session_id] = {
        "id": session_id,
        "siteId": siteId,
        "machineId": machineId,
        "status": "open",
        "createdAt": utc_now(),
        "turns": [],
    }
    return {"id": session_id, "status": "open"}


@router.post("/sessions/{voice_session_id}/turns")
async def voice_turn(
    voice_session_id: str,
    audio: UploadFile = File(...),
    machineId: str | None = Form(None),
    mode: str = Form("ask"),
    siteId: str = Form("main_site"),
):
    audio_bytes = await audio.read()
    machine_context = store.get_machine(machineId) if machineId else None
    result = await process_voice_turn(audio_bytes, audio.filename or "voice.webm", machine_context, site_id=siteId)
    session = store.voice_sessions.setdefault(voice_session_id, {"id": voice_session_id, "status": "open", "turns": []})
    session["turns"].append({"mode": mode, **result, "createdAt": utc_now()})
    return result


@router.get("/sessions/{voice_session_id}")
def get_voice_session(voice_session_id: str):
    return store.voice_sessions.get(voice_session_id, {"id": voice_session_id, "status": "missing", "turns": []})

