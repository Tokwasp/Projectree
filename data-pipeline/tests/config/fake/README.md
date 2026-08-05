# Fake profile

Copy `.env.example.fake` to a local, ignored `.env` only for deterministic
tests or offline demonstrations. Every AI adapter is fake and
`NO_EXTERNAL_AI_CALLS=1` is mandatory. This profile does not prove production
provider connectivity, credit availability, AWS permissions or PostgreSQL
performance.
