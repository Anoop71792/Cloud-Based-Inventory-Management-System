
resource "aws_instance" "inventory" {
  ami           = var.ami_id
  instance_type = var.instance_type

  subnet_id = data.aws_subnet.ec2.id

  vpc_security_group_ids = [
    data.aws_security_group.ec2.id
  ]

  key_name = data.aws_key_pair.existing.key_name

  iam_instance_profile = data.aws_iam_instance_profile.existing.name

  associate_public_ip_address = true

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name        = "Inventory-server"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}
