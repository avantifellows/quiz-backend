resource "cloudflare_record" "cdn_cname" {
  zone_id = data.dotenv.env_file.env["CLOUDFLARE_ZONE_ID"]
  name    = data.dotenv.env_file.env["CLOUDFLARE_CNAME"]
  value   = aws_cloudfront_distribution.backend_cdn.domain_name // The value from the CloudFront output
  type    = "CNAME"
  proxied = false
}
