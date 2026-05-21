-- Omni9 AI/RAG support tables.
-- Idempotent: safe to run more than once.

CREATE SCHEMA IF NOT EXISTS omni9;
SET search_path TO omni9, public;

CREATE TABLE IF NOT EXISTS ai_context_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}',
  embedding_model TEXT,
  embedding_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ai_context_documents_site_idx ON ai_context_documents (site_id, machine_id);
CREATE INDEX IF NOT EXISTS ai_context_documents_created_idx ON ai_context_documents (site_id, created_at DESC);

DROP TRIGGER IF EXISTS ai_context_documents_set_updated_at ON ai_context_documents;
CREATE TRIGGER ai_context_documents_set_updated_at BEFORE UPDATE ON ai_context_documents FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO ai_context_documents (site_id, machine_id, title, body, tags)
VALUES
  (
    'main_site',
    'compressor_a7',
    'Compressor A7 inspection guide',
    'If Compressor A7 shows high vibration with rising temperature, inspect bearing housing, mounting bolts, belt alignment, fan airflow, and lubricant condition before restarting. Use safe-stop if vibration remains above configured protection limits.',
    ARRAY['inspection','compressor','safety']
  ),
  (
    'main_site',
    NULL,
    'Technician language policy',
    'Omni9 should explain machine problems in simple user-friendly language. Avoid MQTT topics, raw node identifiers, API names, or database terms unless the user asks for advanced details.',
    ARRAY['ux','assistant','policy']
  ),
  (
    'main_site',
    NULL,
    'Evidence handling policy',
    'Photos, videos, voice recordings, generated reports, and exported logs are stored in SeaweedFS. PostgreSQL stores metadata only. The mobile app must request signed upload and download URLs through FastAPI.',
    ARRAY['storage','evidence','seaweedfs']
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_migrations (version)
VALUES ('002_ai_rag')
ON CONFLICT (version) DO NOTHING;
