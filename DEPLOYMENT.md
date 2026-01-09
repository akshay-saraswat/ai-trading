# AWS ECS Deployment Guide

Deploy your AI Trading Bot to AWS ECS using **CloudFormation** (Infrastructure as Code).

## Prerequisites

1. **AWS CLI installed and configured**
   ```bash
   aws configure
   ```

2. **Docker installed and running**

3. **jq installed** (for JSON parsing)
   ```bash
   # macOS
   brew install jq

   # Linux
   sudo apt-get install jq
   ```

## Quick Start

### Deploy Everything (One Command)

```bash
# Make script executable
chmod +x deploy-cloudformation.sh

# Deploy infrastructure + application
./deploy-cloudformation.sh
```

This single command:
1. ✅ Creates VPC, subnets, ALB, security groups
2. ✅ Creates ECS cluster, service, task definition
3. ✅ Creates IAM roles with proper permissions
4. ✅ Creates ECR repository
5. ✅ Builds Docker image for AMD64
6. ✅ Pushes to ECR
7. ✅ Deploys to ECS with zero-downtime

### View Deployment Info

```bash
cd cloudformation
./manage-stack.sh outputs
```

Output:
```
Application URL:
  http://ai-trading-alb-XXXXX.us-east-1.elb.amazonaws.com

ECS Cluster:
  ai-trading-cluster

ECS Service:
  ai-trading-service
```

### Access Your Application

Open the ALB URL in your browser.

---

## Configuration

### Environment Variables

Set these before deploying:

```bash
# Infrastructure
export STACK_NAME="ai-trading-stack"           # CloudFormation stack name
export AWS_REGION="us-east-1"                  # AWS region
export PROJECT_NAME="ai-trading"               # Resource naming prefix
export ECR_REPO_NAME="ai-trading-v2"          # ECR repository name

# Application
export MAX_POSITION_SIZE="10000"              # Max $ per trade
export SKIP_MARKET_SCHEDULE_CHECK="false"     # true = trade anytime
export DESIRED_TASK_COUNT="1"                 # Number of ECS tasks (0-10)

# Deploy
./deploy-cloudformation.sh
```

### Robinhood Credentials

**Important:** Use AWS Secrets Manager for credentials. See [ROBINHOOD-SETUP.md](ROBINHOOD-SETUP.md) for detailed setup.

---

## Stack Management

### View Stack Status

```bash
cd cloudformation
./manage-stack.sh status
```

### View Recent Events

```bash
cd cloudformation
./manage-stack.sh events
```

### View Logs

```bash
cd cloudformation
./manage-stack.sh logs
```

### Check Configuration Drift

```bash
cd cloudformation
./manage-stack.sh drift
```

### Delete Everything

```bash
cd cloudformation
./manage-stack.sh delete
```

⚠️ **Warning:** This deletes all resources (VPC, ALB, ECS, IAM, ECR, logs)

---

## Update Application

After making code changes:

```bash
./deploy-cloudformation.sh
```

CloudFormation automatically:
- Detects what changed
- Updates only modified resources
- Performs zero-downtime rolling update
- Rolls back on failure

---

## Monitoring & Troubleshooting

### View Logs

```bash
# Real-time logs
cd cloudformation
./manage-stack.sh logs

# Or directly
aws logs tail /ecs/ai-trading-task --follow --region us-east-1
```

### Check Service Status

```bash
cd cloudformation
./manage-stack.sh status
```

### Check ECS Service Health

```bash
aws ecs describe-services \
  --cluster ai-trading-cluster \
  --services ai-trading-service \
  --region us-east-1 \
  --query 'services[0].[serviceName,status,runningCount,desiredCount]' \
  --output table
```

### Common Issues

#### 1. Stack Creation Failed

```bash
# View failure reason
cd cloudformation
./manage-stack.sh events

# Delete failed stack and retry
./manage-stack.sh delete
cd ..
./deploy-cloudformation.sh
```

#### 2. Health Check Failing

```bash
# Check target group health
TG_ARN=$(aws cloudformation describe-stacks \
  --stack-name ai-trading-stack \
  --query 'Stacks[0].Resources[?LogicalResourceId==`TargetGroup`].PhysicalResourceId' \
  --output text)

aws elbv2 describe-target-health --target-group-arn $TG_ARN
```

Common causes:
- Container not listening on port 80
- `/api/health` endpoint not responding
- Container crashed after startup

#### 3. Tasks Not Starting

```bash
# Check stopped tasks
aws ecs list-tasks \
  --cluster ai-trading-cluster \
  --desired-status STOPPED \
  --region us-east-1

# Get stopped reason
aws ecs describe-tasks \
  --cluster ai-trading-cluster \
  --tasks <TASK_ARN> \
  --query 'tasks[0].stoppedReason'
```

Common causes:
- Docker image doesn't exist in ECR (run `./deploy-cloudformation.sh`)
- IAM permissions missing
- Environment variables incorrect

#### 4. No Docker Image in ECR

```bash
# Build and push manually
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
```

---

## Cost Estimation

Monthly costs (us-east-1):

| Resource | Cost |
|----------|------|
| Fargate (0.5 vCPU, 1GB, 24/7) | $15-20 |
| Application Load Balancer | $20-25 |
| Data Transfer | $5-10 |
| ECR Storage (<5GB) | $0.50 |
| CloudWatch Logs | $2-5 |
| **Total** | **~$45-60/month** |

### Cost Optimization

- **Use Fargate Spot**: Up to 70% cheaper, less reliable
- **Scale to 0 when not trading**: Set `DESIRED_TASK_COUNT=0`
- **Use NLB instead of ALB**: Cheaper, but no HTTP routing
- **Reduce log retention**: Change from 7 days to 1 day

---

## Infrastructure Resources

The CloudFormation stack creates:

### Networking (7 resources)
- VPC (10.0.0.0/16)
- Internet Gateway
- 2 Public Subnets (different AZs)
- Route Table
- 2 Security Groups

### Load Balancing (3 resources)
- Application Load Balancer
- Target Group (health checks)
- HTTP Listener

### Container Infrastructure (5 resources)
- ECS Cluster
- ECS Service
- ECS Task Definition
- ECR Repository
- CloudWatch Log Group

### IAM (2 resources)
- Task Execution Role
- Task Role

**Total: 17 resources**

---

## CI/CD Integration

### GitHub Actions Example

Create `.github/workflows/deploy.yml`:

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

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Deploy to ECS
        run: ./deploy-cloudformation.sh
        env:
          MAX_POSITION_SIZE: 10000
          SKIP_MARKET_SCHEDULE_CHECK: false
```

---

## Documentation

- [CloudFormation README](cloudformation/README.md) - Complete CloudFormation guide
- [Robinhood Setup](ROBINHOOD-SETUP.md) - Credential configuration
- [Architecture](ARCHITECTURE.md) - System architecture
- [Strategies](STRATEGIES.md) - Trading strategies

---

## Need Help?

- AWS CloudFormation Docs: https://docs.aws.amazon.com/cloudformation/
- AWS ECS Docs: https://docs.aws.amazon.com/ecs/
- Check CloudWatch Logs: `cd cloudformation && ./manage-stack.sh logs`
- Review stack events: `cd cloudformation && ./manage-stack.sh events`
