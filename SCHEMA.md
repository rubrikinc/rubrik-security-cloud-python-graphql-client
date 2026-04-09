# Schema Generation

`src/rsc/schema.py` is auto-generated from SDL files committed to `schemas/`. It should never be edited by hand.

## How it works

1. A GraphQL SDL file is added to `schemas/` with the filename `YYYYMMDD.graphql`
2. Pushing that file to `main` triggers the CI workflow (`.github/workflows/schema-update.yml`)
3. CI converts the SDL to an introspection JSON (required by the installed version of sgqlc), generates `src/rsc/schema.py`, bumps the package version to `YYYY.M.D`, commits, tags, and publishes to PyPI

## Adding a new schema

```bash
# Export the SDL from RSC and save it with today's date
cp ~/Downloads/rsc-schema.graphql schemas/$(date +%Y%m%d).graphql

git add schemas/
git commit -m "schema: add YYYYMMDD"
git push origin main
```

CI takes it from there.

## Generating locally

If you need to regenerate `schema.py` without going through CI:

```bash
pip install sgqlc graphql-core

# Convert SDL to introspection JSON (sgqlc requires JSON, not SDL)
python3 - <<'EOF'
import json
from graphql import build_schema, introspection_from_schema

with open("schemas/YYYYMMDD.graphql") as f:
    schema = build_schema(f.read())

with open("/tmp/rsc_schema.json", "w") as f:
    json.dump({"data": introspection_from_schema(schema)}, f)
EOF

python3 -m sgqlc.codegen schema /tmp/rsc_schema.json src/rsc/schema.py
```

## Versioning

Package versions follow the format `X.Y.YYYYMMDD` (e.g., `1.0.20260316` for `schemas/20260316.graphql`).

- **YYYYMMDD** — bumped automatically by CI on each new schema file
- **X.Y** — bumped manually when the library API itself has breaking (major) or additive (minor) changes
