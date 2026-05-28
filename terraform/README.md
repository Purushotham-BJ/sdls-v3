# Terraform — One-Command AWS Deploy

## Prerequisites
- Terraform >= 1.5 (`brew install terraform`)
- AWS CLI configured (`aws configure`)
- EC2 key pair created (`aws ec2 create-key-pair --key-name sdls-key ...`)

## Usage

```bash
# 1. Upload project zip to S3 (Terraform creates the bucket, upload after plan)
#    See step 3 below.

# 2. Deploy all infrastructure
cd terraform/
terraform init
terraform plan \
  -var="key_name=sdls-key" \
  -var="your_ip=$(curl -s ifconfig.me)"
terraform apply \
  -var="key_name=sdls-key" \
  -var="your_ip=$(curl -s ifconfig.me)"

# 3. Upload project zip to the created S3 bucket
BUCKET=$(terraform output -raw s3_bucket)
aws s3 cp ../sdls-v3.zip s3://$BUCKET/sdls-v3.zip

# 4. Trigger user-data re-run (or just wait ~10 min for first boot)
#    Check System 3 logs:
SYS3=$(terraform output -raw system3_public_ip)
ssh -i ~/.ssh/sdls-key.pem ubuntu@$SYS3 "sudo cat /var/log/sdls-userdata.log"

# 5. Get dashboard password
$(terraform output -raw retrieve_password)

# 6. Open dashboard
echo "Dashboard: $(terraform output -raw dashboard_url)"
```

## Destroy
```bash
terraform destroy -var="key_name=sdls-key" -var="your_ip=$(curl -s ifconfig.me)"
```
