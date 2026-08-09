output "bucket_name" {
  description = "Bucket the deploy script syncs static files into."
  value       = aws_s3_bucket.static.bucket
}

output "distribution_id" {
  description = "Distribution ID, needed to create an invalidation after a deploy."
  value       = aws_cloudfront_distribution.this.id
}

output "domain_name" {
  description = "CloudFront domain, e.g. d111111abcdef8.cloudfront.net."
  value       = aws_cloudfront_distribution.this.domain_name
}

output "url" {
  description = "The public URL."
  value       = "https://${aws_cloudfront_distribution.this.domain_name}"
}
