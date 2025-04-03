#!/bin/sh

# EDIT following paramters with correct stack id and region
export STACK_ID=EDIT_ME
export AWS_DEFAULT_REGION=us-east-1

export GEN_AI_ECS_CLUSTER_PREFIX=GenAISamplesECSCluster
export GEN_AI_ECS_SERVICE_PREFIX=GenAISamplesECSService
export SUFFIX_ID=`echo $STACK_ID | cut -d '/' -f 3 | cut -d '-' -f 4 `

aws ecs update-service --region ${AWS_DEFAULT_REGION} \
	--cluster "${GEN_AI_ECS_CLUSTER_PREFIX}-${SUFFIX_ID}"  \
	--service "${GEN_AI_ECS_SERVICE_PREFIX}-${SUFFIX_ID}"  \
	--force-new-deployment --query 'service'.'serviceName'
