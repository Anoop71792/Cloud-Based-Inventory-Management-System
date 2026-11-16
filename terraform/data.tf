data "aws_vpc" "existing" {
  id = var.vpc_id
}

data "aws_subnet" "ec2" {
  id = var.ec2_subnet_id
}

data "aws_iam_instance_profile" "existing" {
  name = var.instance_profile
}

data "aws_key_pair" "existing" {
  key_name = var.key_name
}

data "aws_ecr_repository" "existing" {
  name = "inventory-management-system"
}

data "aws_subnets" "existing" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }
}