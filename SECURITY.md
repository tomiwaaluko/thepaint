# Security Policy

## Supported Versions

This project is actively developed on the default branch and release/deploy branch workflow. Security fixes are generally applied to the latest active code.

## Threat model and known posture

Read this before reporting — several things below are deliberate design
decisions, not oversights.

### The API is intentionally unauthenticated

Every read endpoint (`/v1/players/…`, `/v1/teams/…`, `/v1/games/…`, `/v1/props`,
`/v1/fantasy`) is anonymously accessible. There is no API key, no bearer token,
and no session. `/docs`, `/redoc`, and `/openapi.json` are public and describe
the full API surface.

This is the single most consequential fact about the system's posture and it
was previously unstated here. It is a deliberate choice — the data is
predictions over public sports statistics — but it means:

- The only controls on the expensive inference endpoints are rate limiting
  (`chalk/api/ratelimit.py`) and caching. Rate limits are keyed on client IP,
  derived using `TRUSTED_PROXY_HOPS`; misconfiguring that setting weakens or
  breaks the limiter.
- "This endpoint returns data without authentication" is not a vulnerability
  report we can act on. "This endpoint returns data it shouldn't" is.

The one exception is `DELETE /v1/games/{game_id}/cache` and the `nocache=true`
query parameter, which require `X-Invalidation-Token`. That token is compared
with `secrets.compare_digest` and both features are disabled entirely when
`CACHE_INVALIDATION_TOKEN` is unset (fail-closed).

### Model artifacts are a trusted input

`models/*.joblib` are loaded with `joblib.load`, which is pickle-based and
therefore executes arbitrary code on load. `chalk/api/main.py` loads all seven
stat models in the FastAPI lifespan hook, so this happens at **web process
startup**, not on first request.

The paths are never derived from request input — `MODEL_DIR` is fixed and the
`stat` name comes from a hardcoded list — so there is no route from an HTTP
request to loading an attacker-chosen file. The exposure is supply chain:
anyone who can modify a committed `.joblib` (repository write access, a merged
malicious PR, a compromised build step) achieves code execution inside the
production API at boot. Treat model artifacts with the same scrutiny as code in
review.

### Other accepted risks

- Rate-limit counters live in Redis and fall back to a per-process counter when
  Redis is unavailable. With multiple replicas the fallback is approximate.
- The local `docker-compose.yml` stack uses well-known credentials
  (`chalk`/`chalk`) and unauthenticated Redis and MLflow. All published ports
  are bound to `127.0.0.1`. It is for local development only — do not expose it.
- Injury-report text from ESPN is passed to a Gemini prompt in
  `chalk/ingestion/injury_fetcher.py`. The output is constrained to known player
  IDs before it reaches the database, so the blast radius is injury-status data
  poisoning rather than code execution.

## Reporting a Vulnerability

Please do not open a public GitHub issue for security vulnerabilities.

Instead, report vulnerabilities privately by contacting the maintainer at:

- Discord: `triumphyou`
- Email: `tomiwaaluko02@gmail.com`

Include:

- A clear description of the issue
- Steps to reproduce (if possible)
- Potential impact
- Any suggested mitigations

You can expect:

- Initial acknowledgment within 72 hours
- Follow-up once the issue is verified
- A coordinated disclosure plan where appropriate

## Security Best Practices for Contributors

- Never commit secrets or credentials
- Validate external inputs and API responses
- Prefer least-privilege access patterns
- Keep dependencies updated and pinned through trusted tooling
