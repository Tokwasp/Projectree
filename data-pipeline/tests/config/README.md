# Environment layouts

The repository root `.env.example` is production-shaped: PostgreSQL, AWS,
Clova, Candidate LLM, Embedding, B-model and the internal API token must be
configured by the deployment environment. It contains no usable secret.

Fake-only development and CI values are isolated under `tests/config/fake/`. Never copy
that profile to production. The real `.env` remains ignored by Git.

`NO_EXTERNAL_AI_CALLS=1` is an emergency and test safety switch. When enabled,
construction of a real LLM, Embedding or B-model client fails before any HTTP
request is attempted.
