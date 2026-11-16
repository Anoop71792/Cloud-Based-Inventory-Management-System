
variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "vpc_id" {
  type    = string
  default = "vpc-0634159ca6c52888a"
}

variable "ec2_subnet_id" {
  type    = string
  default = "subnet-052617036c499d968"
}

variable "ami_id" {
  type    = string
  default = "ami-05fbd65e334e88c16"
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "key_name" {
  type    = string
  default = "test-key-july"
}

variable "instance_profile" {
  type    = string
  default = "InventoryAppEC2Role"
}

variable "db_identifier" {
  type    = string
  default = "inventory-mysql-db"
}

variable "db_name" {
  type    = string
  default = "inventorydb"
}

variable "db_username" {
  type    = string
  default = "dbadmin"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_engine_version" {
  type    = string
  default = "8.0.46"
}

variable "aws_profile" {
  type    = string
  default = "anoop-admin"
}