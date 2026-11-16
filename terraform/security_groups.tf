
data "aws_security_group" "ec2" {
  id = "sg-07c0c45aa05193615"
}

data "aws_security_group" "rds" {
  id = "sg-048083776d9b6efbe"
}
