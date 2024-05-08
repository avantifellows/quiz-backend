
# Internet Gateway
resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
}

# route table for public subnet - connecting to Internet gateway
resource "aws_route_table" "rt_public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
}

# associate the route table with public subnet 1
resource "aws_route_table_association" "rta1" {
  subnet_id      = aws_subnet.subnet_1.id
  route_table_id = aws_route_table.rt_public.id
}
# associate the route table with public subnet 2
resource "aws_route_table_association" "rta2" {
  subnet_id      = aws_subnet.subnet_1a.id
  route_table_id = aws_route_table.rt_public.id
}
