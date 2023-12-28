# Elastic IP for NAT gateway
resource "aws_eip" "qb_eip" {
  depends_on = [aws_internet_gateway.qb_gw]
  vpc        = true
  tags = {
    Name = "qb-EIP-for-NAT"
  }
}

# NAT Gateway for private subnets
# (for the private subnet to access internet - eg. ec2 instances downloading softwares from internet)
resource "aws_nat_gateway" "qb_nat_for_private_subnet" {
  allocation_id = aws_eip.qb_eip.id
  subnet_id     = aws_subnet.qb_subnet_1.id
  tags = {
    Name = "qb-NAT-for-private-subnet"
  }
  depends_on = [aws_internet_gateway.qb_gw]
}

# route table for private subnet - connecting to NAT gateway
resource "aws_route_table" "qb_rt_private" {
  vpc_id = aws_vpc.qb_main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.qb_nat_for_private_subnet.id
  }
}

# associate the route table with private subnet
resource "aws_route_table_association" "qb_rta3" {
  subnet_id      = aws_subnet.qb_subnet_2.id
  route_table_id = aws_route_table.qb_rt_private.id
}
