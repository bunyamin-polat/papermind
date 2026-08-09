# `20_app`

The deployable application: a container image on Lambda or App Runner, optionally behind
CloudFront. One configuration, one workspace per environment.

**Its variables come from `slipway.yaml`.** There are no `*.tfvars` files: `deploy.py`
reads that one file, resolves it for the environment, and passes the values as `-var`
flags. An application configures itself in one place, and there is no second place for a
value to be wrong.

Applied by `scripts/deploy.py`, not by hand. The commands below are what that script runs,
written out for when you need to debug it.

## First time in a new clone

```bash
cd terraform/stacks/20_app
cp backend.hcl.example backend.hcl        # bucket name from 00_bootstrap's output
terraform init -backend-config=backend.hcl
terraform workspace new dev               # or: terraform workspace select dev
```

## Deploying

```bash
uv run python scripts/deploy.py dev
uv run python scripts/deploy.py dev --plan   # show what would change, do nothing
```

Which is: build the image for `linux/amd64` without attestations → push it to ECR tagged
with the git SHA → `terraform apply` with the variables from `slipway.yaml` → sync static
files and invalidate the CDN if there is one → print the URL.

## Destroying

```bash
uv run python scripts/destroy.py dev
```

Every environment you cannot confidently destroy is a subscription you did not intend to
buy. Run it, check the console is clean, then deploy again — if destroy does not work, the
step is not finished.

## Workspaces

`default` is refused: a `postcondition` on the caller-identity data source fails with a
message telling you to select one. Without that guard an absent-minded apply creates
`slipway-default-app` and files it in the wrong state.

State is stored per workspace under `env:/<workspace>/20_app/terraform.tfstate`, so dev
and prod cannot collide.

## Rollback

The image tag is a git SHA, so rolling back is applying an older one:

```bash
uv run python scripts/deploy.py dev --tag <older-sha>
```

No rebuild — the image is still in ECR, subject to the lifecycle policy that keeps the
last ten.

## What this stack does not create

- **A budget.** There is one already, account-wide, from `00_bootstrap`. A second one per
  environment would count the same spend twice.
- **A data bucket or secrets.** The example app stores nothing and reads no secrets. Those
  modules get written when something actually needs them; an unused bucket is real cost
  and a real cleanup debt in exchange for proving nothing.
