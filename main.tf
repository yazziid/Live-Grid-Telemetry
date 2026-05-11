data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }
}

data "aws_caller_identity" "current" {}

resource "aws_security_group" "digital_twin_sg" {
  name        = "digital-twin-sg"
  description = "Allow web traffic to Airflow and Streamlit"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 8501
    to_port     = 8501
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "digital_twin_server" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = "t3.small" 
  
  vpc_security_group_ids = [aws_security_group.digital_twin_sg.id]

  user_data = <<-EOF
              #!/bin/bash
              sudo yum update -y
              sudo yum install -y docker
              sudo systemctl enable docker
              sudo systemctl start docker
              sudo usermod -aG docker ec2-user
              sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
              sudo chmod +x /usr/local/bin/docker-compose
              EOF

  tags = {
    Name = "Digital-Twin-Core-Server"
  }
}

resource "aws_s3_bucket" "datalake" {
  bucket        = "digital-twin-grid-datalake-${data.aws_caller_identity.current.account_id}-v2"
  force_destroy = true 
}

resource "aws_sqs_queue" "telemetry_queue" {
  name                      = "grid-telemetry-queue"
  message_retention_seconds = 86400 
}

resource "aws_dynamodb_table" "grid_state_table" {
  name           = "GridTelemetryState"
  billing_mode   = "PAY_PER_REQUEST" 
  hash_key       = "MetricID"        
  range_key      = "Timestamp"      

  attribute {
    name = "MetricID"
    type = "S"
  }

  attribute {
    name = "Timestamp"
    type = "N" # Number (Unix epoch time)
  }

  ttl {
    attribute_name = "TimeToLive"
    enabled        = true
  }

  tags = {
    Environment = "Portfolio-Project"
    Project     = "Renewable-Digital-Twin"
  }
}

output "server_public_ip" {
  value = aws_instance.digital_twin_server.public_ip
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.grid_state_table.name
}