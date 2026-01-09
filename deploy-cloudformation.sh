#!/bin/bash

# Deploy AI Trading Bot using AWS CloudFormation
# This script:
# 1. Ensures ECR repository exists
# 2. Builds and pushes Docker image to ECR
# 3. Creates/updates CloudFormation stack (infrastructure)
# 4. Forces new ECS deployment if stack already exists

set -e

# Configuration
STACK_NAME="${STACK_NAME:-ai-trading-stack}"
AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="${PROJECT_NAME:-ai-trading}"
ECR_REPO_NAME="${ECR_REPO_NAME:-ai-trading}"

# Parameters
MAX_POSITION_SIZE="${MAX_POSITION_SIZE:-10000}"
SKIP_MARKET_SCHEDULE_CHECK="${SKIP_MARKET_SCHEDULE_CHECK:-false}"
DESIRED_TASK_COUNT="${DESIRED_TASK_COUNT:-1}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 Deploying AI Trading Bot with CloudFormation${NC}"
echo ""

# Get AWS account ID
echo -e "${YELLOW}📋 Getting AWS account ID...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_URI="${ECR_REGISTRY}/${ECR_REPO_NAME}"
echo -e "${GREEN}✓ AWS Account ID: $AWS_ACCOUNT_ID${NC}"
echo -e "${GREEN}✓ ECR URI: $ECR_URI${NC}"
echo ""

# Step 1: Ensure ECR repository exists
echo -e "${YELLOW}📦 Checking ECR repository...${NC}"
ECR_EXISTS=$(aws ecr describe-repositories \
  --repository-names $ECR_REPO_NAME \
  --region $AWS_REGION \
  --query 'repositories[0].repositoryName' \
  --output text 2>/dev/null || echo "")

if [ -z "$ECR_EXISTS" ]; then
  echo -e "${YELLOW}Creating ECR repository...${NC}"
  aws ecr create-repository \
    --repository-name $ECR_REPO_NAME \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true \
    --tags Key=Project,Value=$PROJECT_NAME \
    > /dev/null
  echo -e "${GREEN}✓ ECR repository created${NC}"
else
  echo -e "${GREEN}✓ ECR repository exists${NC}"
fi
echo ""

# Step 2: Build and push Docker image BEFORE creating stack
echo -e "${YELLOW}🔨 Building Docker image for AMD64...${NC}"
docker buildx build --platform linux/amd64 -t $ECR_REPO_NAME:latest . --load
echo -e "${GREEN}✓ Docker image built${NC}"

echo -e "${YELLOW}🔐 Logging into Amazon ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY
echo -e "${GREEN}✓ Logged into ECR${NC}"

echo -e "${YELLOW}📤 Pushing image to ECR...${NC}"
docker tag $ECR_REPO_NAME:latest $ECR_URI:latest
docker push $ECR_URI:latest
echo -e "${GREEN}✓ Image pushed to ECR: $ECR_URI:latest${NC}"
echo ""

# Step 3: Check if stack exists
STACK_EXISTS=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].StackName' \
  --output text 2>/dev/null || echo "")

if [ -z "$STACK_EXISTS" ]; then
  echo -e "${YELLOW}📦 Stack does not exist. Creating new stack...${NC}"
  STACK_ACTION="create-stack"
  WAIT_CONDITION="stack-create-complete"
  IS_NEW_STACK=true
else
  echo -e "${YELLOW}📦 Stack exists. Updating stack...${NC}"
  STACK_ACTION="update-stack"
  WAIT_CONDITION="stack-update-complete"
  IS_NEW_STACK=false
fi

# Step 4: Deploy CloudFormation stack (now image exists in ECR)
echo -e "${YELLOW}☁️  Deploying CloudFormation stack...${NC}"

if [ "$STACK_ACTION" = "create-stack" ]; then
  aws cloudformation create-stack \
    --stack-name $STACK_NAME \
    --template-body file://cloudformation/ecs-infrastructure.yaml \
    --parameters \
      ParameterKey=ProjectName,ParameterValue=$PROJECT_NAME \
      ParameterKey=ECRRepositoryName,ParameterValue=$ECR_REPO_NAME \
      ParameterKey=MaxPositionSize,ParameterValue=$MAX_POSITION_SIZE \
      ParameterKey=SkipMarketScheduleCheck,ParameterValue=$SKIP_MARKET_SCHEDULE_CHECK \
      ParameterKey=DesiredTaskCount,ParameterValue=$DESIRED_TASK_COUNT \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION \
    --tags Key=Project,Value=$PROJECT_NAME

  echo -e "${GREEN}✓ Stack creation initiated${NC}"
else
  # Try to update, but ignore error if no changes
  set +e
  UPDATE_OUTPUT=$(aws cloudformation update-stack \
    --stack-name $STACK_NAME \
    --template-body file://cloudformation/ecs-infrastructure.yaml \
    --parameters \
      ParameterKey=ProjectName,ParameterValue=$PROJECT_NAME \
      ParameterKey=ECRRepositoryName,ParameterValue=$ECR_REPO_NAME \
      ParameterKey=MaxPositionSize,ParameterValue=$MAX_POSITION_SIZE \
      ParameterKey=SkipMarketScheduleCheck,ParameterValue=$SKIP_MARKET_SCHEDULE_CHECK \
      ParameterKey=DesiredTaskCount,ParameterValue=$DESIRED_TASK_COUNT \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION 2>&1)

  UPDATE_EXIT_CODE=$?
  set -e

  if [ $UPDATE_EXIT_CODE -ne 0 ]; then
    if echo "$UPDATE_OUTPUT" | grep -q "No updates are to be performed"; then
      echo -e "${GREEN}✓ No stack updates needed${NC}"
      WAIT_CONDITION=""
    else
      echo -e "${RED}✗ Stack update failed:${NC}"
      echo "$UPDATE_OUTPUT"
      exit 1
    fi
  else
    echo -e "${GREEN}✓ Stack update initiated${NC}"
  fi
fi

# Wait for stack operation to complete
if [ ! -z "$WAIT_CONDITION" ]; then
  echo -e "${YELLOW}⏳ Waiting for stack operation to complete...${NC}"
  aws cloudformation wait $WAIT_CONDITION \
    --stack-name $STACK_NAME \
    --region $AWS_REGION
  echo -e "${GREEN}✓ Stack operation completed${NC}"
fi
echo ""

# Get stack outputs
echo -e "${YELLOW}📤 Getting stack outputs...${NC}"
ECS_CLUSTER=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`ECSClusterName`].OutputValue' \
  --output text)

ECS_SERVICE=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`ECSServiceName`].OutputValue' \
  --output text)

ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`ALBDNS`].OutputValue' \
  --output text)

echo -e "${GREEN}✓ ECR Repository: $ECR_URI${NC}"
echo -e "${GREEN}✓ ECS Cluster: $ECS_CLUSTER${NC}"
echo -e "${GREEN}✓ ECS Service: $ECS_SERVICE${NC}"
echo -e "${GREEN}✓ ALB DNS: $ALB_DNS${NC}"
echo ""

# Step 5: Force new ECS deployment if stack was updated (not created)
if [ "$IS_NEW_STACK" = false ] && [ ! -z "$ECS_SERVICE" ]; then
  echo -e "${YELLOW}🔄 Forcing new ECS deployment with updated image...${NC}"
  aws ecs update-service \
    --cluster $ECS_CLUSTER \
    --service $ECS_SERVICE \
    --force-new-deployment \
    --region $AWS_REGION \
    > /dev/null

  echo -e "${GREEN}✓ ECS service deployment initiated${NC}"

  echo -e "${YELLOW}⏳ Waiting for deployment to stabilize...${NC}"
  aws ecs wait services-stable \
    --cluster $ECS_CLUSTER \
    --services $ECS_SERVICE \
    --region $AWS_REGION

  echo -e "${GREEN}✓ Deployment stabilized${NC}"
fi

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo -e "${YELLOW}📊 Deployment Summary:${NC}"
echo -e "  Stack: ${GREEN}$STACK_NAME${NC}"
echo -e "  Region: ${GREEN}$AWS_REGION${NC}"
echo -e "  Cluster: ${GREEN}$ECS_CLUSTER${NC}"
echo -e "  Service: ${GREEN}$ECS_SERVICE${NC}"
echo -e "  Image: ${GREEN}$ECR_URI:latest${NC}"
echo ""
echo -e "${YELLOW}🌐 Access your application:${NC}"
echo -e "  ${GREEN}http://$ALB_DNS${NC}"
echo ""
echo -e "${YELLOW}🔗 View in AWS Console:${NC}"
CONSOLE_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`ConsoleUrl`].OutputValue' \
  --output text)
echo "  $CONSOLE_URL"
echo ""
echo -e "${YELLOW}📝 View CloudWatch Logs:${NC}"
echo "  aws logs tail /ecs/${PROJECT_NAME}-task --follow --region $AWS_REGION"
echo ""
