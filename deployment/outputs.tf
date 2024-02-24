output "load_balancer_dns_name" {
  value = aws_lb.lb.dns_name
  description = "The DNS name of the load balancer"
}
