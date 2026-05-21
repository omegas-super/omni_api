from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from openai import OpenAI

from app.config import get_settings
from app.services.ai_agent import answer_question, expand_measurement_units
from app.services.storage import upload_bytes


def audio_client() -> OpenAI:
    settings = get_settings()
    if not settings.resolved_audio_api_key:
        raise RuntimeError("AUDIO_API_KEY is required for NagaAI speech services")
    return OpenAI(base_url=settings.resolved_audio_base_url, api_key=settings.resolved_audio_api_key)


def _speech_response_bytes(response) -> bytes:
    if hasattr(response, "read"):
        return response.read()
    if hasattr(response, "content"):
        return response.content

    with NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        response.stream_to_file(path)
        return path.read_bytes()
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def synthesize_reply(text: str, site_id: str, machine_id: str | None = None) -> dict | None:
    settings = get_settings()
    if not text.strip():
        return None
    try:
        response = audio_client().audio.speech.create(
            model=settings.tts_model,
            voice=settings.tts_voice,
            input=expand_measurement_units(text),
        )
        audio_bytes = _speech_response_bytes(response)
        if not audio_bytes:
            return None
        uploaded = upload_bytes(
            site_id=site_id,
            machine_id=machine_id,
            kind="audio",
            filename="omni-reply.mp3",
            content_type="audio/mpeg",
            content=audio_bytes,
        )
        return {"audioUrl": uploaded["downloadUrl"], "storageKey": uploaded["storageKey"], "contentType": "audio/mpeg"}
    except Exception as exc:
        return {"audioUrl": None, "error": str(exc)}


async def process_voice_turn(audio_bytes: bytes, filename: str, machine_context: dict | None = None, site_id: str = "main_site") -> dict:
    settings = get_settings()
    machine_id = machine_context.get("id") if machine_context else None

    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename or "voice.webm"

    try:
        transcript = audio_client().audio.transcriptions.create(
            model=settings.stt_model,
            file=audio_file,
            prompt=None,
            language=None,
        )
        text = getattr(transcript, "text", "") or ""
    except Exception as exc:
        text = ""
        assistant = answer_question(
            site_id=site_id,
            machine_id=machine_id,
            message="Voice transcription failed. Tell the user to retry and summarize the focused machine in one short line.",
            mode="voice_transcription_failed",
        )
        return {
            "userTranscript": "",
            "assistantText": assistant["assistantText"],
            "audioUrl": None,
            "model": assistant["model"],
            "target": assistant["target"],
            "transcriptionError": str(exc),
        }

    assistant = answer_question(
        site_id=site_id,
        machine_id=machine_id,
        message=text or "No clear speech detected. Summarize the focused machine in one short line and ask for a clearer question.",
        mode="voice",
    )
    speech = synthesize_reply(assistant["assistantText"], site_id=site_id, machine_id=machine_id)

    return {
        "userTranscript": text,
        "assistantText": assistant["assistantText"],
        "audioUrl": (speech or {}).get("audioUrl"),
        "audio": speech,
        "model": assistant["model"],
        "target": assistant["target"],
        "contextSummary": assistant.get("contextSummary"),
    }
