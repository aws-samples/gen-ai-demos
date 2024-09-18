#!/bin/sh
set -xv
# EDIT following paramters
export STACK_ID=EDIT_ME
export AWS_ACCOUNT_ID=EDIT_ME
export AWS_DEFAULT_REGION=us-west-2 # EDIT_ME

export GEN_AI_ECS_CLUSTER_PREFIX=GenAISamplesECSCluster
export GEN_AI_ECS_SERVICE_PREFIX=GenAISamplesECSService
export SUFFIX_ID=`echo $STACK_ID | cut -d '/' -f 3 | cut -d '-' -f 4 `

export TASK_DEFINITION=`aws ecs list-task-definitions --family-prefix "GenAISamplesTask-${SUFFIX_ID}"  | jq  -r '.taskDefinitionArns[0]'`

aws ecs describe-task-definition --task-definition $TASK_DEFINITION --region ${AWS_DEFAULT_REGION}  | jq '.taskDefinition.containerDefinitions[0].environment' > task_defn_env.json
cat task_defn_env.json | jq -r '.[]' | jq '"export \(.name)=\(.value)"' | sed -e 's/^"//;s/=/="/g' > localTestEnv.sh

echo "Setup AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env variable values from SecretsManager for the matching secret name /env/genai/<STACK_NAME>-GenAiDemoUser*"
echo "Then source the localTestEnv.sh script to setup various env variables"

echo "Then run streamlit using python v3.9 "
echo "Streamlit command:  streamlit run App.py --logger.level   info --browser.gatherUsageStats   false --browser.serverAddress   0.0.0.0 --server.enableCORS   false --server.enableXsrfProtection   false --server.enableXsrfProtection   false --server.port 8080 "
