# A VPC that exists so the database can be private — and a NAT gateway that exists
# because making it private has a consequence.
#
# The chain is worth stating plainly, because the first version of this file got it
# wrong. A private RDS instance can only be reached from inside the VPC. Putting Lambda
# or App Runner inside the VPC to reach it also routes their *outbound* traffic through
# the VPC, and the application calls OpenAI. There is no VPC endpoint for a service that
# is not on AWS, so outbound internet needs a NAT gateway.
#
#   NAT gateway   ~$32/month
#   db.t4g.micro  ~$12/month
#
# Keeping the database off the public internet therefore costs more than the database.
# The alternative — `publicly_accessible = true`, defended by a password — cannot be
# narrowed with a security group either, because Lambda's egress addresses are not fixed.
# A database on the internet is not a thing to put in a portfolio, so the NAT stays and
# the number gets published rather than hidden.
#
# One NAT, not one per availability zone. A second would double the cost to protect
# against an AZ failure during a demo that is deliberately short-lived.

locals {
  # Two AZs because RDS requires a subnet group spanning two, even for single-AZ.
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr_block
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = var.name })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, { Name = var.name })
}

# Public subnets hold the NAT gateway and nothing else.
resource "aws_subnet" "public" {
  count = length(local.azs)

  vpc_id                  = aws_vpc.this.id
  availability_zone       = local.azs[count.index]
  cidr_block              = cidrsubnet(var.cidr_block, 4, count.index)
  map_public_ip_on_launch = false

  tags = merge(var.tags, { Name = "${var.name}-public-${local.azs[count.index]}" })
}

resource "aws_subnet" "private" {
  count = length(local.azs)

  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = cidrsubnet(var.cidr_block, 4, count.index + length(local.azs))

  tags = merge(var.tags, { Name = "${var.name}-private-${local.azs[count.index]}" })
}

resource "aws_eip" "nat" {
  count  = var.enable_nat ? 1 : 0
  domain = "vpc"

  tags = merge(var.tags, { Name = "${var.name}-nat" })
}

resource "aws_nat_gateway" "this" {
  count = var.enable_nat ? 1 : 0

  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id

  depends_on = [aws_internet_gateway.this]

  tags = merge(var.tags, { Name = var.name })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(var.tags, { Name = "${var.name}-public" })
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  # Without NAT this table has no default route, so the private subnets can reach the
  # database and nothing else. That is the right shape for a deployment whose compute
  # never needs to call out — it is just not this one.
  dynamic "route" {
    for_each = var.enable_nat ? [1] : []
    content {
      cidr_block     = "0.0.0.0/0"
      nat_gateway_id = aws_nat_gateway.this[0].id
    }
  }

  tags = merge(var.tags, { Name = "${var.name}-private" })
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = aws_subnet.private[*].id

  tags = merge(var.tags, { Name = var.name })
}

# One security group for anything allowed to reach the database. Membership is the grant:
# attach it to a Lambda or an App Runner connector and that client can connect, without a
# CIDR rule naming an address that will change.
resource "aws_security_group" "database_clients" {
  name        = "${var.name}-db-clients"
  description = "Members may connect to the PaperMind database"
  vpc_id      = aws_vpc.this.id

  egress {
    description = "Anywhere: the application calls OpenAI, and that leaves via NAT."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name}-db-clients" })
}

resource "aws_security_group" "database" {
  name        = "${var.name}-db"
  description = "PaperMind database"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Postgres from members of the client group"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.database_clients.id]
  }

  tags = merge(var.tags, { Name = "${var.name}-db" })
}
