terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# Create a 10 GB gp3 volume
resource "aws_ebs_volume" "test_unattached_volume_1" {
  availability_zone = "us-east-1a"
  size              = 10
  type              = "gp3"

  tags = {
    Name = "finops-test-unattached-1"
    Purpose = "FinOps Testing"
  }
}

# Create a 50 GB gp2 volume
resource "aws_ebs_volume" "test_unattached_volume_2" {
  availability_zone = "us-east-1b"
  size              = 50
  type              = "gp2"

  tags = {
    Name = "finops-test-unattached-2"
    Purpose = "FinOps Testing"
  }
}
