#!/bin/bash

# CloudFormation Stack Management Utility
# Quick commands for common stack operations

set -e

STACK_NAME="${STACK_NAME:-ai-trading-stack}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

show_usage() {
  echo "Usage: $0 {status|outputs|events|delete|drift|logs}"
  echo ""
  echo "Commands:"
  echo "  status   - Show stack status"
  echo "  outputs  - Show stack outputs (ALB DNS, URLs, etc.)"
  echo "  events   - Show recent stack events"
  echo "  delete   - Delete the entire stack"
  echo "  drift    - Detect configuration drift"
  echo "  logs     - Tail CloudWatch logs"
  echo ""
  echo "Environment variables:"
  echo "  STACK_NAME  (default: ai-trading-stack)"
  echo "  AWS_REGION  (default: us-east-1)"
  exit 1
}

check_stack_exists() {
  STACK_EXISTS=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].StackName' \
    --output text 2>/dev/null || echo "")

  if [ -z "$STACK_EXISTS" ]; then
    echo -e "${RED}✗ Stack '$STACK_NAME' does not exist${NC}"
    exit 1
  fi
}

cmd_status() {
  check_stack_exists
  echo -e "${BLUE}Stack Status${NC}"
  echo ""
  aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].[StackName,StackStatus,CreationTime,LastUpdatedTime]' \
    --output table
}

cmd_outputs() {
  check_stack_exists
  echo -e "${BLUE}Stack Outputs${NC}"
  echo ""

  ALB_DNS=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ALBDNS`].OutputValue' \
    --output text)

  ALB_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ALBUrl`].OutputValue' \
    --output text)

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

  ECR_URI=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ECRRepositoryUri`].OutputValue' \
    --output text 2>/dev/null || echo "")

  if [ -z "$ECR_URI" ]; then
    ECR_REPO_NAME=$(aws cloudformation describe-stacks \
      --stack-name $STACK_NAME \
      --region $AWS_REGION \
      --query 'Stacks[0].Parameters[?ParameterKey==`ECRRepositoryName`].ParameterValue' \
      --output text 2>/dev/null || echo "")

    if [ -z "$ECR_REPO_NAME" ]; then
      ECR_REPO_NAME="ai-trading"
    fi

    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
  fi

  CONSOLE_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ConsoleUrl`].OutputValue' \
    --output text)

  echo -e "${YELLOW}Application URL:${NC}"
  echo "  $ALB_URL"
  echo ""
  echo -e "${YELLOW}ALB DNS:${NC}"
  echo "  $ALB_DNS"
  echo ""
  echo -e "${YELLOW}ECS Cluster:${NC}"
  echo "  $ECS_CLUSTER"
  echo ""
  echo -e "${YELLOW}ECS Service:${NC}"
  echo "  $ECS_SERVICE"
  echo ""
  echo -e "${YELLOW}ECR Repository:${NC}"
  echo "  $ECR_URI"
  echo ""
  echo -e "${YELLOW}AWS Console:${NC}"
  echo "  $CONSOLE_URL"
  echo ""
}

cmd_events() {
  check_stack_exists
  echo -e "${BLUE}Recent Stack Events (last 20)${NC}"
  echo ""
  aws cloudformation describe-stack-events \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'StackEvents[:20].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]' \
    --output table
}

cmd_delete() {
  check_stack_exists
  echo -e "${RED}⚠️  WARNING: This will delete the entire stack and all resources!${NC}"
  echo ""
  echo "Stack: $STACK_NAME"
  echo "Region: $AWS_REGION"
  echo ""
  echo "Resources that will be deleted:"
  echo "  - VPC and all networking"
  echo "  - Application Load Balancer"
  echo "  - ECS Cluster and Service"
  echo "  - ECR Repository (and all images)"
  echo "  - CloudWatch Logs"
  echo "  - IAM Roles"
  echo ""
  read -p "Are you sure? Type 'DELETE' to confirm: " CONFIRM

  if [ "$CONFIRM" != "DELETE" ]; then
    echo -e "${YELLOW}Deletion cancelled${NC}"
    exit 0
  fi

  echo ""
  echo -e "${YELLOW}Deleting stack...${NC}"
  aws cloudformation delete-stack \
    --stack-name $STACK_NAME \
    --region $AWS_REGION

  echo -e "${YELLOW}Waiting for deletion to complete...${NC}"
  aws cloudformation wait stack-delete-complete \
    --stack-name $STACK_NAME \
    --region $AWS_REGION

  echo -e "${GREEN}✓ Stack deleted successfully${NC}"
}

cmd_drift() {
  check_stack_exists
  echo -e "${BLUE}Detecting Configuration Drift${NC}"
  echo ""

  echo -e "${YELLOW}Starting drift detection...${NC}"
  DRIFT_ID=$(aws cloudformation detect-stack-drift \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'StackDriftDetectionId' \
    --output text)

  echo -e "${YELLOW}Waiting for drift detection to complete...${NC}"
  sleep 5

  DRIFT_STATUS=$(aws cloudformation describe-stack-drift-detection-status \
    --stack-drift-detection-id $DRIFT_ID \
    --region $AWS_REGION \
    --query 'DetectionStatus' \
    --output text)

  while [ "$DRIFT_STATUS" = "DETECTION_IN_PROGRESS" ]; do
    sleep 2
    DRIFT_STATUS=$(aws cloudformation describe-stack-drift-detection-status \
      --stack-drift-detection-id $DRIFT_ID \
      --region $AWS_REGION \
      --query 'DetectionStatus' \
      --output text)
  done

  echo ""
  echo -e "${GREEN}✓ Drift detection complete${NC}"
  echo ""

  # Show drift results
  aws cloudformation describe-stack-resource-drifts \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'StackResourceDrifts[?StackResourceDriftStatus!=`IN_SYNC`].[LogicalResourceId,StackResourceDriftStatus,ResourceType]' \
    --output table

  DRIFT_COUNT=$(aws cloudformation describe-stack-resource-drifts \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'length(StackResourceDrifts[?StackResourceDriftStatus!=`IN_SYNC`])' \
    --output text)

  if [ "$DRIFT_COUNT" = "0" ]; then
    echo -e "${GREEN}No drift detected - all resources match template${NC}"
  else
    echo -e "${RED}Found $DRIFT_COUNT drifted resource(s)${NC}"
  fi
}

cmd_logs() {
  check_stack_exists
  echo -e "${BLUE}Tailing CloudWatch Logs${NC}"
  echo ""

  PROJECT_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Parameters[?ParameterKey==`ProjectName`].ParameterValue' \
    --output text)

  LOG_GROUP="/ecs/${PROJECT_NAME}-task"

  echo -e "${YELLOW}Log Group: $LOG_GROUP${NC}"
  echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
  echo ""

  aws logs tail $LOG_GROUP --follow --region $AWS_REGION
}

# Main
if [ $# -eq 0 ]; then
  show_usage
fi

case "$1" in
  status)
    cmd_status
    ;;
  outputs)
    cmd_outputs
    ;;
  events)
    cmd_events
    ;;
  delete)
    cmd_delete
    ;;
  drift)
    cmd_drift
    ;;
  logs)
    cmd_logs
    ;;
  *)
    echo -e "${RED}Unknown command: $1${NC}"
    echo ""
    show_usage
    ;;
esac
