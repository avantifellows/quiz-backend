data "cloudflare_zone" "main" {
  name = var.cloudflare_zone_name
}

resource "cloudflare_record" "quiz_backend" {
  zone_id = data.cloudflare_zone.main.id
  name    = "quiz-backend"
  content = aws_lb.quiz_backend.dns_name
  type    = "CNAME"
  proxied = true
  comment = "Quiz backend ${var.environment} - points to ALB"
}

# ALB only has an HTTP listener (port 80). The zone-level SSL mode is likely
# "Full", which makes Cloudflare connect to the origin over HTTPS. This page
# rule overrides SSL to "Flexible" for just this hostname so Cloudflare
# connects to the ALB over HTTP.
resource "cloudflare_page_rule" "ssl_flexible" {
  zone_id  = data.cloudflare_zone.main.id
  target   = "quiz-backend.${var.cloudflare_zone_name}/*"
  priority = 1

  actions {
    ssl = "flexible"
  }
}
