
output "ec2_instance_id" {
  value = aws_instance.inventory.id
}

output "ec2_public_ip" {
  value = aws_instance.inventory.public_ip
}

output "ec2_public_dns" {
  value = aws_instance.inventory.public_dns
}

output "ec2_security_group_id" {
  value = data.aws_security_group.ec2.id
}

output "rds_identifier" {
  value = aws_db_instance.inventory.identifier
}

output "rds_endpoint" {
  value = aws_db_instance.inventory.address
}

output "rds_port" {
  value = aws_db_instance.inventory.port
}

output "rds_database_name" {
  value = aws_db_instance.inventory.db_name
}

output "rds_security_group_id" {
  value = data.aws_security_group.rds.id
}

output "ecr_repository_uri" {
  value = data.aws_ecr_repository.existing.repository_url
}

output "iam_instance_profile" {
  value = data.aws_iam_instance_profile.existing.name
}

output "ec2_ssh_command" {
  value = "ssh -i test-key-july.pem ec2-user@${aws_instance.inventory.public_ip}"
}