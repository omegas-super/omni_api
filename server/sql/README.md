# Omni9 SQL

The initial PostgreSQL migration is in `server/sql/001_initial_schema.sql`.

## Apply Schema

Do not commit real passwords. Set the connection string in your shell, then run:

```bash
psql "$OMNI9_DATABASE_URL" -v ON_ERROR_STOP=1 -f server/sql/001_initial_schema.sql
```

On this Windows machine, `psql.exe` was found at:

```text
C:\Program Files\PostgreSQL\18\bin\psql.exe
```

## What It Creates

Schema: `omni9`

Core tables:

```text
sites
users
app_sessions
machines
readings
alerts
actions
work_orders
impact_records
media_assets
mesh_gateways
mesh_nodes
notification_events
automation_rules
voice_sessions
voice_turns
schema_migrations
```

Views:

```text
app_machine_cards
site_health_summary
```

Seed data includes one site, three demo machines, first readings, one site hub, mesh nodes, an alert, automation rules, and impact records.

## Garage Storage

Garage stores the actual files. PostgreSQL stores metadata in `omni9.media_assets`:

```text
storage_driver = garage
storage_bucket = omni9-media
storage_key = sites/main_site/evidence/...
```

The app should request upload/download URLs from FastAPI. It should not talk directly to Garage.

See `docs/GARAGE_STORAGE_SETUP.md` for bucket/key setup.
