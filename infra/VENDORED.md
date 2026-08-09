# Vendored from Slipway

Everything under `infra/modules/` and `infra/stacks/` except the modules listed below was
**copied** from [Slipway](https://github.com/bunyamin-polat/slipway) at setup time. It is
owned by this repository from that moment on.

Terraform can reference modules remotely — `source = "git::https://github.com/…"` — and
that is deliberately not done. A remote source would tie every deployment here to another
repository's main branch, so a change made in Slipway could break this one without anyone
touching it. The cost of copying is that a fix has to be carried across by hand; the
benefit is that nothing here breaks because of work done somewhere else.

| Module | Origin |
|---|---|
| `lambda_container` | Slipway |
| `apprunner_service` | Slipway |
| `budget` | Slipway |
| `observability` | Slipway |
| `static_site` | Slipway (unused here — no static assets yet) |
| **`network`** | **Written here** |
| **`rds_postgres`** | **Written here** |

## Why `network` and `rds_postgres` were written rather than copied

Slipway has neither. Its reference application is stateless, so it needed no database and
therefore no VPC. PaperMind is the first consumer with 294 MB of corpus behind it, and
that is what exposed the gap.

They stay here rather than going back into Slipway on purpose. The rule is that a module
is promoted into the blueprint when a **second** project needs it — Assay, Winnow, Chart
and Cadence all want Postgres, so promotion is likely, but "likely" is not "proven". A
module written for one consumer and generalised for four imagined ones is how a blueprint
turns into a speculative platform that everything waits on. Writing it here first means
this repository is never blocked, and the promotion decision gets made against evidence.
