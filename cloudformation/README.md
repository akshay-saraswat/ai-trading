# CloudFormation Deployment Guide

Deploy your AI Trading Bot to AWS ECS using Infrastructure as Code.

## Why CloudFormation?

✅ **Better than bash scripts:**
- Idempotent - run multiple times safely
- Atomic rollback on failure
- Drift detection
- Change preview (change sets)
- Clean deletion of all resources
- Version controlled infrastructure

## Quick Start

### 1. Deploy Infrastructure + Application

```bash
# Make script executable
chmod +x deploy-cloudformation.sh

# Deploy everything (first time or updates)
./deploy-cloudformation.sh
```

This single command:
1. ✅ Creates/updates complete infrastructure (VPC, ALB, ECS, IAM)
2. ✅ Builds Docker image for AMD64
3. ✅ Pushes to ECR
4. ✅ Deploys to ECS with zero-downtime

### 2. Access Your Application

After deployment completes, you'll see:
```
🌐 Access your application:
  http://ai-trading-alb-XXXXX.us-east-1.elb.amazonaws.com
```

## Configuration

### Environment Variables

Set before running `deploy-cloudformation.sh`:

```bash
# Stack Configuration
export STACK_NAME="ai-trading-stack"           # CloudFormation stack name
export AWS_REGION="us-east-1"                  # AWS region
export PROJECT_NAME="ai-trading"               # Resource naming prefix
export ECR_REPO_NAME="ai-trading-v2"          # ECR repository name

# Application Configuration
export MAX_POSITION_SIZE="10000"              # Max $ per trade
export SKIP_MARKET_SCHEDULE_CHECK="false"     # true = trade anytime
export DESIRED_TASK_COUNT="1"                 # Number of ECS tasks
```

### Robinhood Credentials

**Option 1: AWS Secrets Manager (Recommended)**

See [ROBINHOOD-SETUP.md](../ROBINHOOD-SETUP.md) for complete guide.

**Option 2: CloudFormation Parameters (Less Secure)**

```bash
aws cloudformation create-stack \
  --stack-name ai-trading-stack \
  --template-body file://cloudformation/ecs-infrastructure.yaml \
  --parameters \
    ParameterKey=RobinhoodUsername,ParameterValue=your_username \
    ParameterKey=RobinhoodPassword,ParameterValue=your_password \
  --capabilities CAPABILITY_NAMED_IAM
```

## Stack Operations

### Create Stack

```bash
# Using script
./deploy-cloudformation.sh

# Or manually
aws cloudformation create-stack \
  --stack-name ai-trading-stack \
  --template-body file://cloudformation/ecs-infrastructure.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### Update Stack

```bash
# Using script (automatically detects update)
./deploy-cloudformation.sh

# Or manually
aws cloudformation update-stack \
  --stack-name ai-trading-stack \
  --template-body file://cloudformation/ecs-infrastructure.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### Preview Changes (Change Set)

```bash
# Create change set
aws cloudformation create-change-set \
  --stack-name ai-trading-stack \
  --change-set-name my-changes \
  --template-body file://cloudformation/ecs-infrastructure.yaml \
  --capabilities CAPABILITY_NAMED_IAM

# View changes
aws cloudformation describe-change-set \
  --stack-name ai-trading-stack \
  --change-set-name my-changes

# Apply changes
aws cloudformation execute-change-set \
  --stack-name ai-trading-stack \
  --change-set-name my-changes
```

### View Stack Status

```bash
aws cloudformation describe-stacks \
  --stack-name ai-trading-stack \
  --query 'Stacks[0].[StackName,StackStatus]' \
  --output table
```

### View Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name ai-trading-stack \
  --query 'Stacks[0].Outputs'
```

### View Stack Events (Logs)

```bash
aws cloudformation describe-stack-events \
  --stack-name ai-trading-stack \
  --query 'StackEvents[:10].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId]' \
  --output table
```

### Delete Stack (Cleanup)

```bash
# Delete entire infrastructure
aws cloudformation delete-stack \
  --stack-name ai-trading-stack \
  --region us-east-1

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete \
  --stack-name ai-trading-stack \
  --region us-east-1
```

⚠️ **Note**: This deletes ALL resources (VPC, ALB, ECS, IAM, ECR images, logs)

## Update Application Only (No Infrastructure Changes)

If you only changed code and don't need infrastructure updates:

```bash
# Build and push new image
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/ai-trading-v2"

docker buildx build --platform linux/amd64 -t ai-trading-v2:latest . --load
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_URI
docker tag ai-trading-v2:latest $ECR_URI:latest
docker push $ECR_URI:latest

# Force new deployment
aws ecs update-service \
  --cluster ai-trading-cluster \
  --service ai-trading-service \
  --force-new-deployment \
  --region us-east-1

# Wait for deployment
aws ecs wait services-stable \
  --cluster ai-trading-cluster \
  --services ai-trading-service \
  --region us-east-1
```

## Stack Resources

The CloudFormation stack creates:

### Networking (7 resources)
- VPC (10.0.0.0/16)
- Internet Gateway
- 2 Public Subnets (us-east-1a, us-east-1b)
- Route Table
- 2 Security Groups (ALB, ECS Tasks)

### Load Balancing (3 resources)
- Application Load Balancer
- Target Group (health checks /api/health)
- HTTP Listener (port 80)

### Container Infrastructure (5 resources)
- ECS Cluster
- ECS Service
- ECS Task Definition
- ECR Repository
- CloudWatch Log Group

### IAM (2 resources)
- Task Execution Role (ECR pull, CloudWatch logs)
- Task Role (Bedrock, Secrets Manager)

**Total: 17 resources**

## Cost Estimate

Monthly costs (us-east-1):

| Resource | Cost |
|----------|------|
| Fargate (0.5 vCPU, 1GB, 24/7) | $15-20 |
| Application Load Balancer | $20-25 |
| Data Transfer | $5-10 |
| ECR Storage (<5GB) | $0.50 |
| CloudWatch Logs | $2-5 |
| **Total** | **~$45-60/month** |

## Troubleshooting

### Stack Creation Failed

```bash
# View failure events
aws cloudformation describe-stack-events \
  --stack-name ai-trading-stack \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'

# Delete failed stack
aws cloudformation delete-stack --stack-name ai-trading-stack
```

### Stack Update Failed (Rollback)

CloudFormation automatically rolls back to previous working state.

```bash
# View rollback events
aws cloudformation describe-stack-events \
  --stack-name ai-trading-stack \
  --query 'StackEvents[:20]'
```

### Stack Stuck in UPDATE_ROLLBACK_FAILED

```bash
# Continue rollback (skip failed resources)
aws cloudformation continue-update-rollback \
  --stack-name ai-trading-stack
```

### ECS Tasks Not Starting

```bash
# Check service events
aws ecs describe-services \
  --cluster ai-trading-cluster \
  --services ai-trading-service \
  --query 'services[0].events[:5]'

# Check stopped tasks
aws ecs list-tasks \
  --cluster ai-trading-cluster \
  --desired-status STOPPED \
  --query 'taskArns[:3]' \
  | xargs -I {} aws ecs describe-tasks \
      --cluster ai-trading-cluster \
      --tasks {}
```

### Health Check Failing

```bash
# Check ALB target health
TG_ARN=$(aws cloudformation describe-stacks \
  --stack-name ai-trading-stack \
  --query 'Stacks[0].Resources[?LogicalResourceId==`TargetGroup`].PhysicalResourceId' \
  --output text)

aws elbv2 describe-target-health --target-group-arn $TG_ARN
```

## Drift Detection

Check if resources were manually modified:

```bash
# Start drift detection
aws cloudformation detect-stack-drift \
  --stack-name ai-trading-stack

# View drift status
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id <id-from-above>

# View drifted resources
aws cloudformation describe-stack-resource-drifts \
  --stack-name ai-trading-stack \
  --query 'StackResourceDrifts[?StackResourceDriftStatus==`MODIFIED`]'
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy to ECS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Deploy CloudFormation
        run: ./deploy-cloudformation.sh
        env:
          MAX_POSITION_SIZE: 10000
          SKIP_MARKET_SCHEDULE_CHECK: false
```

## Migration from Bash Scripts

If you previously used `setup-ecs-infrastructure.sh`:

1. **Delete old resources** (if desired):
   ```bash
   # List all resources with project tag
   aws resourcegroupstaggingapi get-resources \
     --tag-filters Key=Name,Values=ai-trading-*
   ```

2. **Deploy with CloudFormation**:
   ```bash
   ./deploy-cloudformation.sh
   ```

3. **Verify outputs match**:
   - ALB DNS
   - ECS cluster/service names
   - ECR repository

## Advanced Configuration

### Custom VPC CIDR

Edit [ecs-infrastructure.yaml](ecs-infrastructure.yaml):
```yaml
VPC:
  Type: AWS::EC2::VPC
  Properties:
    CidrBlock: 10.1.0.0/16  # Change this
```

### Enable HTTPS

1. Request ACM certificate
2. Add to CloudFormation:
```yaml
ALBListenerHTTPS:
  Type: AWS::ElasticLoadBalancingV2::Listener
  Properties:
    LoadBalancerArn: !Ref ApplicationLoadBalancer
    Port: 443
    Protocol: HTTPS
    Certificates:
      - CertificateArn: arn:aws:acm:...
    DefaultActions:
      - Type: forward
        TargetGroupArn: !Ref TargetGroup
```

### Auto Scaling

Add to CloudFormation:
```yaml
ServiceScalingTarget:
  Type: AWS::ApplicationAutoScaling::ScalableTarget
  Properties:
    ServiceNamespace: ecs
    ResourceId: !Sub 'service/${ECSCluster}/${ECSService.Name}'
    ScalableDimension: ecs:service:DesiredCount
    MinCapacity: 1
    MaxCapacity: 10
```

---

**Questions?**
- CloudFormation Docs: https://docs.aws.amazon.com/cloudformation/
- Template Reference: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-reference.html
