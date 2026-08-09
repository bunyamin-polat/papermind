# PostgreSQL with pgvector, private, and as small as the corpus allows.
#
# Slipway has no database module because its reference application is stateless. This is
# the gap PaperMind found by being the blueprint's first real consumer.
#
# Sizing is from measurement, not from a default: the corpus is 294 MB, of which 241 MB
# is the HNSW index and the vectors it covers. db.t4g.micro has 1 GB of RAM, which holds
# the working set with room to spare, and is the cheapest instance that supports the
# Postgres 17 engine.

locals {
  # pgvector ships with RDS PostgreSQL as an available extension; the app enables it via
  # `CREATE EXTENSION vector`, exactly as it does against the local container. Nothing
  # here installs it, which is the point — the same schema.sql runs in both places.
  engine_version = "17"
}

# Generated, stored, and never printed. Terraform state holds it either way, which is why
# the state bucket is encrypted and private — but at least it is not in a variable file,
# a shell history, or a CI log.
resource "random_password" "master" {
  length  = 32
  special = false # RDS rejects several punctuation characters in master passwords
}

resource "aws_secretsmanager_secret" "database" {
  name                    = "${var.name}/database"
  description             = "PaperMind database connection details"
  recovery_window_in_days = var.secret_recovery_days

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
    host     = aws_db_instance.this.address
    port     = aws_db_instance.this.port
    dbname   = var.database_name
    url = format(
      "postgresql://%s:%s@%s:%s/%s",
      var.master_username,
      random_password.master.result,
      aws_db_instance.this.address,
      aws_db_instance.this.port,
      var.database_name,
    )
  })
}

resource "aws_db_instance" "this" {
  identifier = var.name

  engine         = "postgres"
  engine_version = local.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.database_name
  username = var.master_username
  password = random_password.master.result

  db_subnet_group_name   = var.db_subnet_group_name
  vpc_security_group_ids = [var.security_group_id]
  # Private. A database reachable from the internet and defended by a password is not a
  # thing to put in a portfolio, whatever the password is.
  publicly_accessible = false

  # Single-AZ on purpose. Multi-AZ doubles the bill to protect a corpus that can be
  # rebuilt from the arXiv API in half an hour, and saying so is more honest than paying
  # for a resilience this workload does not need.
  multi_az = false

  backup_retention_period = var.backup_retention_days
  skip_final_snapshot     = var.skip_final_snapshot
  final_snapshot_identifier = (
    var.skip_final_snapshot ? null : "${var.name}-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"
  )
  deletion_protection = var.deletion_protection

  auto_minor_version_upgrade   = true
  performance_insights_enabled = false # not free on t4g.micro

  tags = var.tags

  lifecycle {
    # `final_snapshot_identifier` uses timestamp(), which changes on every plan and would
    # otherwise show a permanent diff.
    ignore_changes = [final_snapshot_identifier]
  }
}
