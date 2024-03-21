#!/bin/sh

# EDIT following paramters
export STACK_ID=EDIT_ME
export AWS_ACCOUNT_ID=EDIT_ME
export AWS_DEFAULT_REGION=us-east-1
export GEN_AI_SAMPLE_ECR_REPO=gen-ai-sample-repo # EDIT as necessary
export GEN_AI_SAMPLE_DOCKER_VERSION=0.1 # EDIT as necessary

export SUFFIX_ID=`echo $STACK_ID | cut -d '/' -f 3 | cut -d '-' -f 4 `
export GEN_AI_SAMPLE_DOCKER_IMAGE="gen-ai-sample-${SUFFIX_ID}"
export REPO_ID="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${GEN_AI_SAMPLE_ECR_REPO}/${GEN_AI_SAMPLE_DOCKER_IMAGE}"

#aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${GEN_AI_SAMPLE_ECR_REPO}/${GEN_AI_SAMPLE_DOCKER_IMAGE}

docker build -t $GEN_AI_SAMPLE_DOCKER_IMAGE:$GEN_AI_SAMPLE_DOCKER_VERSION . 
docker tag "${GEN_AI_SAMPLE_DOCKER_IMAGE}:${GEN_AI_SAMPLE_DOCKER_VERSION}"  "${REPO_ID}:${GEN_AI_SAMPLE_DOCKER_VERSION}"
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${REPO_ID}
docker push "${REPO_ID}:${GEN_AI_SAMPLE_DOCKER_VERSION}"


