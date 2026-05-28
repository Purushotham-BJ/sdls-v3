# ═══════════════════════════════════════════════════════════════════════════
# SDLS v3 — Terraform Infrastructure
# Creates: VPC, subnet, IGW, route table, security group, 3 EC2 instances,
#          S3 bucket for project zip, SSM parameters, IAM role + instance profile
#
# Usage:
#   1. terraform init
#   2. terraform plan -var="key_name=sdls-key" -var="your_ip=$(curl -s ifconfig.me)"
#   3. terraform apply
# ═══════════════════════════════════════════════════════════════════════════

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Variables ─────────────────────────────────────────────────────────────
variable "aws_region"          { default = "us-east-1" }
variable "key_name"            { description = "EC2 key pair name" }
variable "your_ip"             { description = "Your public IP for SSH (x.x.x.x)" }
variable "instance_type"       { default = "t3.small" }
variable "dashboard_password"  { default = "" }  # empty = auto-generated
variable "project_name"        { default = "sdls-v3" }

# ── Data Sources ───────────────────────────────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-*"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
}

# ── VPC + Networking ───────────────────────────────────────────────────────
resource "aws_vpc" "sdls" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "${var.project_name}-vpc" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.sdls.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true
  tags = { Name = "${var.project_name}-subnet" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.sdls.id
  tags   = { Name = "${var.project_name}-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.sdls.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "${var.project_name}-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Security Group ─────────────────────────────────────────────────────────
resource "aws_security_group" "sdls" {
  name        = "${var.project_name}-sg"
  description = "SDLS v3 distributed system"
  vpc_id      = aws_vpc.sdls.id

  # SSH — your IP only
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["${var.your_ip}/32"]
  }

  # Dashboard — public
  ingress {
    from_port   = 5006
    to_port     = 5006
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # All service ports — VPC internal only
  ingress {
    from_port   = 5000
    to_port     = 5005
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
  ingress {
    from_port   = 5007
    to_port     = 5010
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  # Redis + MongoDB — VPC internal only
  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
  ingress {
    from_port   = 27017
    to_port     = 27017
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-sg" }
}

# ── IAM Role for EC2 (S3 + SSM access) ───────────────────────────────────
resource "aws_iam_role" "sdls_ec2" {
  name = "${var.project_name}-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "sdls_ec2_policy" {
  name = "${var.project_name}-ec2-policy"
  role = aws_iam_role.sdls_ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.artifacts.arn,
          "${aws_s3_bucket.artifacts.arn}/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = [
          "ssm:GetParameter",
          "ssm:PutParameter",
          "ssm:DeleteParameter"
        ]
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter/sdls/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "sdls_ec2" {
  name = "${var.project_name}-instance-profile"
  role = aws_iam_role.sdls_ec2.name
}

# ── S3 Bucket for project artifacts ───────────────────────────────────────
resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${var.project_name}-artifacts-"
  force_destroy = true
  tags = { Name = "${var.project_name}-artifacts" }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── EC2 Instances ─────────────────────────────────────────────────────────
locals {
  userdata = {
    system3 = base64encode(templatefile("${path.module}/../scripts/userdata-system3.sh", {
      bucket = aws_s3_bucket.artifacts.bucket
    }))
    system2 = base64encode(templatefile("${path.module}/../scripts/userdata-system2.sh", {
      bucket = aws_s3_bucket.artifacts.bucket
    }))
    system1 = base64encode(templatefile("${path.module}/../scripts/userdata-system1.sh", {
      bucket = aws_s3_bucket.artifacts.bucket
    }))
  }
}

resource "aws_instance" "system3" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.sdls.id]
  iam_instance_profile   = aws_iam_instance_profile.sdls_ec2.name
  user_data_base64       = local.userdata.system3

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = { Name = "${var.project_name}-system3", Role = "infra" }
}

resource "aws_instance" "system2" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.sdls.id]
  iam_instance_profile   = aws_iam_instance_profile.sdls_ec2.name
  user_data_base64       = local.userdata.system2

  root_block_device {
    volume_size = 15
    volume_type = "gp3"
  }

  tags = { Name = "${var.project_name}-system2", Role = "payment-inventory" }
  depends_on = [aws_instance.system3]
}

resource "aws_instance" "system1" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.sdls.id]
  iam_instance_profile   = aws_iam_instance_profile.sdls_ec2.name
  user_data_base64       = local.userdata.system1

  root_block_device {
    volume_size = 15
    volume_type = "gp3"
  }

  tags = { Name = "${var.project_name}-system1", Role = "gateway-orders" }
  depends_on = [aws_instance.system3]
}

# ── Outputs ───────────────────────────────────────────────────────────────
output "system3_public_ip"    { value = aws_instance.system3.public_ip }
output "system3_private_ip"   { value = aws_instance.system3.private_ip }
output "system2_public_ip"    { value = aws_instance.system2.public_ip }
output "system1_public_ip"    { value = aws_instance.system1.public_ip }
output "dashboard_url"        { value = "http://${aws_instance.system3.public_ip}:5006" }
output "api_gateway_url"      { value = "http://${aws_instance.system1.public_ip}:5000" }
output "s3_bucket"            { value = aws_s3_bucket.artifacts.bucket }
output "ssh_system3"          { value = "ssh -i ~/.ssh/${var.key_name}.pem ubuntu@${aws_instance.system3.public_ip}" }
output "retrieve_password"    {
  value = "aws ssm get-parameter --name /sdls/dashboard_password --with-decryption --query Parameter.Value --output text"
}
