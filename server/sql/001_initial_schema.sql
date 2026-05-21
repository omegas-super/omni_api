-- Omni9 initial PostgreSQL schema.
-- Idempotent: safe to run more than once.

CREATE SCHEMA IF NOT EXISTS omni9;
SET search_path TO omni9, public;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sites (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT REFERENCES sites(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner', 'manager', 'technician', 'viewer')),
  password_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  device_name TEXT,
  push_token TEXT,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS machines (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  area TEXT,
  state TEXT NOT NULL DEFAULT 'healthy' CHECK (state IN ('healthy', 'watch', 'critical', 'protected', 'offline')),
  protection_mode TEXT NOT NULL DEFAULT 'standard' CHECK (protection_mode IN ('standard', 'early', 'very_early')),
  safe_stop_enabled BOOLEAN NOT NULL DEFAULT true,
  vibration_limit_g NUMERIC NOT NULL DEFAULT 8.5,
  current_limit_a NUMERIC NOT NULL DEFAULT 16.0,
  temperature_limit_c NUMERIC NOT NULL DEFAULT 90.0,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS readings (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  machine_id TEXT NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
  temperature_c NUMERIC,
  humidity_pct NUMERIC,
  vibration_g NUMERIC,
  current_a NUMERIC,
  safe_stopped BOOLEAN NOT NULL DEFAULT false,
  machine_enabled BOOLEAN NOT NULL DEFAULT true,
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS readings_machine_time_idx ON readings (machine_id, created_at DESC);
CREATE INDEX IF NOT EXISTS readings_site_time_idx ON readings (site_id, created_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info', 'watch', 'critical')),
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  acknowledged_at TIMESTAMPTZ,
  cleared_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS alerts_site_time_idx ON alerts (site_id, created_at DESC);
CREATE INDEX IF NOT EXISTS alerts_open_idx ON alerts (site_id, cleared_at) WHERE cleared_at IS NULL;

CREATE TABLE IF NOT EXISTS actions (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  type TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('device', 'backend', 'ai', 'user', 'gateway')),
  reason TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS actions_site_time_idx ON actions (site_id, created_at DESC);

CREATE TABLE IF NOT EXISTS work_orders (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'done', 'cancelled')),
  priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
  assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
  due_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS impact_records (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  metric TEXT NOT NULL CHECK (metric IN ('downtime_prevented', 'energy_saved', 'co2_avoided', 'maintenance_prevented')),
  value NUMERIC NOT NULL,
  unit TEXT NOT NULL,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS media_assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  storage_driver TEXT NOT NULL DEFAULT 's3',
  storage_bucket TEXT,
  storage_key TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT,
  kind TEXT NOT NULL DEFAULT 'evidence' CHECK (kind IN ('photo', 'video', 'audio', 'report', 'log', 'evidence')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mesh_gateways (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('online', 'weak', 'offline')),
  ws_connected BOOLEAN NOT NULL DEFAULT false,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mesh_nodes (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  gateway_id TEXT REFERENCES mesh_gateways(id) ON DELETE SET NULL,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  mesh_node_id TEXT,
  friendly_name TEXT NOT NULL,
  coverage_state TEXT NOT NULL DEFAULT 'offline' CHECK (coverage_state IN ('good', 'weak', 'offline')),
  peer_count INTEGER NOT NULL DEFAULT 0,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mesh_nodes_site_idx ON mesh_nodes (site_id, coverage_state);

CREATE TABLE IF NOT EXISTS notification_events (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  read_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notification_user_time_idx ON notification_events (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS automation_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  trigger_type TEXT NOT NULL,
  action_type TEXT NOT NULL,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS voice_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  machine_id TEXT REFERENCES machines(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS voice_turns (
  id BIGSERIAL PRIMARY KEY,
  voice_session_id UUID NOT NULL REFERENCES voice_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  transcript TEXT,
  audio_asset_id UUID REFERENCES media_assets(id) ON DELETE SET NULL,
  model TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS voice_turns_session_time_idx ON voice_turns (voice_session_id, created_at ASC);
SET search_path TO omni9, public;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS sites_set_updated_at ON sites;
CREATE TRIGGER sites_set_updated_at BEFORE UPDATE ON sites FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS users_set_updated_at ON users;
CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS machines_set_updated_at ON machines;
CREATE TRIGGER machines_set_updated_at BEFORE UPDATE ON machines FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS work_orders_set_updated_at ON work_orders;
CREATE TRIGGER work_orders_set_updated_at BEFORE UPDATE ON work_orders FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS mesh_gateways_set_updated_at ON mesh_gateways;
CREATE TRIGGER mesh_gateways_set_updated_at BEFORE UPDATE ON mesh_gateways FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS mesh_nodes_set_updated_at ON mesh_nodes;
CREATE TRIGGER mesh_nodes_set_updated_at BEFORE UPDATE ON mesh_nodes FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS automation_rules_set_updated_at ON automation_rules;
CREATE TRIGGER automation_rules_set_updated_at BEFORE UPDATE ON automation_rules FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE VIEW app_machine_cards AS
SELECT
  m.id,
  m.site_id,
  m.name,
  m.area,
  m.state,
  m.protection_mode,
  m.safe_stop_enabled,
  m.last_seen_at,
  r.temperature_c,
  r.vibration_g,
  r.current_a,
  COALESCE(mn.coverage_state, 'offline') AS coverage_state,
  COALESCE(mn.peer_count, 0) AS peer_count
FROM machines m
LEFT JOIN LATERAL (
  SELECT temperature_c, vibration_g, current_a
  FROM readings
  WHERE readings.machine_id = m.id
  ORDER BY created_at DESC
  LIMIT 1
) r ON true
LEFT JOIN LATERAL (
  SELECT coverage_state, peer_count
  FROM mesh_nodes
  WHERE mesh_nodes.machine_id = m.id
  ORDER BY last_seen_at DESC NULLS LAST
  LIMIT 1
) mn ON true;

CREATE OR REPLACE VIEW site_health_summary AS
SELECT
  s.id AS site_id,
  s.name AS site_name,
  COUNT(DISTINCT m.id) AS machine_count,
  COUNT(DISTINCT m.id) FILTER (WHERE m.state = 'critical') AS critical_count,
  COUNT(DISTINCT m.id) FILTER (WHERE m.state = 'protected') AS protected_count,
  COUNT(DISTINCT a.id) FILTER (WHERE a.cleared_at IS NULL) AS open_alert_count
FROM sites s
LEFT JOIN machines m ON m.site_id = s.id
LEFT JOIN alerts a ON a.site_id = s.id
GROUP BY s.id, s.name;

INSERT INTO sites (id, name)
VALUES ('main_site', 'Main Site')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO users (site_id, name, email, role)
VALUES ('main_site', 'Omni9 Operator', 'operator@omni9.local', 'owner')
ON CONFLICT (email) DO NOTHING;

INSERT INTO machines (id, site_id, name, area, state, protection_mode, vibration_limit_g, current_limit_a, temperature_limit_c)
VALUES
  ('compressor_a7', 'main_site', 'Compressor A7', 'Line 2', 'critical', 'early', 6.8, 12.8, 72.0),
  ('pump_stack_b2', 'main_site', 'Pump Stack B2', 'Water loop', 'watch', 'standard', 8.5, 16.0, 90.0),
  ('conveyor_rail_4', 'main_site', 'Conveyor Rail 4', 'Packaging', 'healthy', 'standard', 8.5, 16.0, 90.0)
ON CONFLICT (id) DO NOTHING;

INSERT INTO readings (site_id, machine_id, temperature_c, vibration_g, current_a, raw_payload)
VALUES
  ('main_site', 'compressor_a7', 82.4, 8.6, 14.2, '{"seed":true}'::jsonb),
  ('main_site', 'pump_stack_b2', 57.8, 4.3, 8.8, '{"seed":true}'::jsonb),
  ('main_site', 'conveyor_rail_4', 38.1, 1.7, 3.5, '{"seed":true}'::jsonb);

INSERT INTO mesh_gateways (id, site_id, name, status)
VALUES ('mesh_gateway_01', 'main_site', 'Site Hub 01', 'offline')
ON CONFLICT (id) DO NOTHING;

INSERT INTO mesh_nodes (id, site_id, gateway_id, machine_id, mesh_node_id, friendly_name, coverage_state, peer_count)
VALUES
  ('mesh_node_compressor_a7', 'main_site', 'mesh_gateway_01', 'compressor_a7', '123456', 'Compressor A7 link', 'good', 3),
  ('mesh_node_pump_stack_b2', 'main_site', 'mesh_gateway_01', 'pump_stack_b2', '123457', 'Pump Stack B2 link', 'weak', 1)
ON CONFLICT (id) DO NOTHING;

INSERT INTO alerts (site_id, machine_id, severity, title, body, target_type, target_id)
VALUES ('main_site', 'compressor_a7', 'critical', 'Protection ready', 'Compressor A7 needs attention before the next cycle.', 'machine', 'compressor_a7');

INSERT INTO automation_rules (site_id, name, trigger_type, action_type, config)
VALUES
  ('main_site', 'Protect on critical vibration', 'critical_vibration', 'safe_stop', '{"mode":"automatic"}'::jsonb),
  ('main_site', 'Notify on weak coverage', 'weak_coverage', 'notify', '{"target":"technician"}'::jsonb),
  ('main_site', 'Attach inspection evidence', 'inspection_complete', 'attach_evidence', '{}'::jsonb);

INSERT INTO impact_records (site_id, machine_id, metric, value, unit, reason)
VALUES
  ('main_site', 'compressor_a7', 'downtime_prevented', 4.2, 'h', 'Demo seed: protected compressor before bearing failure'),
  ('main_site', 'compressor_a7', 'energy_saved', 12.8, 'kWh', 'Demo seed: avoided stalled motor run'),
  ('main_site', 'compressor_a7', 'co2_avoided', 6.1, 'kg', 'Demo seed: reduced wasted energy');

INSERT INTO schema_migrations (version)
VALUES ('001_initial_schema')
ON CONFLICT (version) DO NOTHING;
