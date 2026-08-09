# Container registry for the application image.
#
# One repository, shared by every environment. Environments are told apart by image
# tag, not by having a registry each — a repository per environment triples the
# storage and gives you three places to forget to clean up.

resource "aws_ecr_repository" "app" {
  name = coalesce(var.ecr_repository_name, "${var.project}-app")

  # MUTABLE so a tag like `dev` can be moved to a newer image. IMMUTABLE is stricter
  # and worth it once deploys are addressed by digest, but it also makes re-pushing
  # after a failed deploy an error rather than a retry.
  image_tag_mutability = "MUTABLE"

  # Basic scanning is free and catches known CVEs in the base image.
  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  # Without this, `terraform destroy` fails on a repository that still holds images —
  # and then the repository survives, quietly billing for storage.
  force_delete = var.ecr_force_delete
}

# Container images are hundreds of megabytes each and ECR charges $0.10/GB/month.
# Twenty untagged layers from failed builds is a real line on a real bill.
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.ecr_untagged_expire_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_expire_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the most recent ${var.ecr_max_image_count} images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.ecr_max_image_count
        }
        action = { type = "expire" }
      },
    ]
  })
}
