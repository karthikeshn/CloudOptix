provider "aws" {
  region = "us-east-1"
}

resource "aws_ebs_volume" "test_unattached" {
  availability_zone = "us-east-1a"
  size              = 8
  type              = "gp3"

  tags = {
    Name = "TestUnattachedVolume"
    Environment = "Dev"
  }
}
