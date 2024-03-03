resource "aws_cloudfront_distribution" "backend_cdn" {
  origin {
    domain_name = aws_lb.lb.dns_name
    origin_id   = aws_lb.lb.dns_name

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled         = true
  is_ipv6_enabled = true

  aliases = [data.dotenv.env_file.env["CLOUDFLARE_CNAME"]]

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = aws_lb.lb.dns_name
    compress               = true
    viewer_protocol_policy = "allow-all"
    cache_policy_id        = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  }

  ordered_cache_behavior {
    path_pattern           = "quiz/*"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    target_origin_id       = aws_lb.lb.dns_name
    compress               = true
    viewer_protocol_policy = "allow-all"
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  ordered_cache_behavior {
    path_pattern           = "questions/*"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    target_origin_id       = aws_lb.lb.dns_name
    compress               = true
    viewer_protocol_policy = "allow-all"
    cache_policy_id        = "083fc51c-4735-4176-8d51-90566f1bb3e7"
  }

  restrictions {
    geo_restriction {
      locations        = []
      restriction_type = "none"
    }
  }

  tags = {
    Name = "${local.environment_prefix}backend-cdn"
  }

  viewer_certificate {
    acm_certificate_arn = "arn:aws:acm:us-east-1:111766607077:certificate/5477789a-3421-407f-b8ce-df2ce8949e48"
    ssl_support_method  = "sni-only"
  }

  price_class = "PriceClass_200"
}
