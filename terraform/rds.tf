
resource "aws_db_subnet_group" "inventory" {
  name       = "stockwise-db-subnet-group"
  subnet_ids = data.aws_subnets.existing.ids

  tags = {
    Name      = "stockwise-db-subnet-group"
    ManagedBy = "Terraform"
  }
}

resource "aws_db_instance" "inventory" {
  identifier = var.db_identifier

  engine         = "mysql"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password
  port     = 3306

  db_subnet_group_name = aws_db_subnet_group.inventory.name

  vpc_security_group_ids = [
    data.aws_security_group.rds.id
  ]

  publicly_accessible = false
  multi_az            = false

  backup_retention_period    = 1
  auto_minor_version_upgrade = true

  deletion_protection = false
  skip_final_snapshot = true

  tags = {
    Name        = "stockwise-mysql-db"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}
