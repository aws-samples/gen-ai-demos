"""
MIT No Attribution

Copyright 2023 Amazon Web Services

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
import json
import os
import boto3
import requests
import sys
import urllib3
from sagemaker import image_uris, model_uris, script_uris
from sagemaker.model import Model, ModelPackage
from sagemaker.jumpstart.model import JumpStartModel


# Lookup the model package arn and related instance type for various models
# using locally cached json
def cache_ai21_model_packages():
    script_dir = os.path.dirname(__file__) #<-- absolute dir the script is in
    ai21_model_package_defn = 'ai21_model_package_arns.json'
    ai21_model_package_path = os.path.join(script_dir, ai21_model_package_defn)
    model_package_file = open(ai21_model_package_path)
    ai21_model_package = json.load(model_package_file)
    #print('#### ai21 model package loaded! ', ai21_model_package)
    return ai21_model_package
   
# Initialize the cache for ai21 model packages
ai21_model_package_json = cache_ai21_model_packages()

    
def get_model_package_arn(model_id,instance_type, region):
    print('Checking for model id: {} with instance type {} and region {}'.format(model_id,instance_type,region))
    
    if model_id.startswith('ai21'):
        return ai21_model_package_json[model_id]['model_package_map'][region]
    
    return 'ARN missing for model!!'


# Reference https://github.com/aws-samples/generative-ai-sagemaker-cdk-demo/blob/main/script/sagemaker_uri.py
def get_sagemaker_uris(model_id,instance_type,region):

    MODEL_VERSION = "*"  # latest
    SCOPE = "inference"

    inference_image_uri = image_uris.retrieve(region=region,
                                          framework=None,
                                          model_id=model_id,
                                          model_version=MODEL_VERSION,
                                          image_scope=SCOPE,
                                          instance_type=instance_type)

    inference_model_uri = model_uris.retrieve(model_id=model_id,
                                          model_version=MODEL_VERSION,
                                          model_scope=SCOPE)

    inference_source_uri = script_uris.retrieve(model_id=model_id,
                                            model_version=MODEL_VERSION,
                                            script_scope=SCOPE)

    model_bucket_name = inference_model_uri.split("/")[2]
    model_bucket_key = "/".join(inference_model_uri.split("/")[3:])
    model_docker_image = inference_image_uri

    return {"model_bucket_name":model_bucket_name, "model_bucket_key": model_bucket_key, \
            "model_docker_image":model_docker_image, "instance_type":instance_type, \
                "inference_source_uri":inference_source_uri, "region":region}

    
def generate_physical_resource_id(event, context):
    aws_region = os.environ['AWS_DEFAULT_REGION']
    aws_account_id = context.invoked_function_arn.split(":")[4]
    
    props = event['ResourceProperties']
    endpoint_name = props['EndpointName']
    
    return f'arn:aws:sagemaker:{aws_region}:{aws_account_id}:endpoint/{endpoint_name}'


def deploy(event, context, model, instance_type, endpoint_name):    
    initial_instance_count=1

    # Default response
    response = {
            'Operation': 'Create',
            'Status': '200',
            'Endpoint': endpoint_name,
            'PhysicalResourceId': generate_physical_resource_id(event, context)
        }
        
    props = event['ResourceProperties']
    model_id = props['ModelId']
    
        
    try:
        
        # Not specifying volume size as some instances reject it like ml.g5.xx -
        # volume_size=100,
        deploy_response = model.deploy(
            initial_instance_count=initial_instance_count,
            instance_type=instance_type,
            model_data_download_timeout=1800,
            container_startup_health_check_timeout=1800,        
            endpoint_name=endpoint_name
        )
        print(deploy_response)
        
        sendResponse(event, context, 'SUCCESS', response)

    except:
        error = sys.exc_info()
        print(error)
        errorMsg = error[1]
        print('Error in deploying model: ', error)
        if ('Cannot create already existing endpoint' in str(errorMsg)):
            sendResponse(event, context, 'SUCCESS', response)
        else:
            response = {
                'Operation': 'Create',
                'Status': '400',
                'Endpoint': endpoint_name,
                'ErrorMessage': str(errorMsg)
            }
            sendResponse(event, context, 'FAILED', response)
    

def deploy_opensoure_model(event, context):    
    aws_region = os.environ['AWS_DEFAULT_REGION']
    aws_account_id = context.invoked_function_arn.split(":")[4]
    
    #model_id = 'huggingface-text2text-flan-t5-xl' # event['model_id']
    #instance_type = 'ml.g5.2xlarge' # event['instance_type']
    
    props = event['ResourceProperties']
    endpoint_name = props['EndpointName']
    model_id = props['ModelId']
    instance_type = props['InstanceType']
    sm_deployer_role_name = props['SMDeployerRole']

    # Role to give SageMaker permission to access AWS services.
    sagemaker_role= f'arn:aws:iam::{aws_account_id}:role/{sm_deployer_role_name}'
    
    # Specify an AWS container image. 
    sagemaker_details = get_sagemaker_uris(model_id,instance_type,aws_region)
    container = sagemaker_details['model_docker_image']
    
    # Create a variable w/ the model S3 URI
    # First, provide the name of your S3 bucket
    s3_bucket = sagemaker_details['model_bucket_name']
    
    # Relative S3 path
    model_s3_key = sagemaker_details['model_bucket_key']
    
    # Combine bucket name, model file name, and relate S3 path to create S3 model URI
    # Need eula acceptance for Llama
    model_url = f's3://{s3_bucket}/{model_s3_key}'                            
    #env = { 'HF_MODEL_ID': model_id, 'MMS_MAX_RESPONSE_SIZE': '20000000', 'CURL_CA_BUNDLE': '', 'accept_eula': 'true' }
    
    print('Model url: ', model_url)
    
    model = None
    
    # No model data for HuggingFace or Llama
    if (model_id.startswith('huggingface-') or model_id.startswith('hf-') ):
            
            #JumpStartModel(model_id=None, model_version=None, 
            # tolerate_vulnerable_model=None, tolerate_deprecated_model=None, 
            # region=None, instance_type=None, 
            # image_uri=None, model_data=None, role=None, 
            # predictor_cls=None, env=None, name=None, vpc_config=None, 
            # sagemaker_session=None, enable_network_isolation=None, 
            # model_kms_key=None, image_config=None, source_dir=None, 
            # code_location=None, entry_point=None, container_log_level=None, 
            # dependencies=None, git_config=None)
        
        model = JumpStartModel(model_id=model_id, 
                                role=sagemaker_role,
                                region=aws_region,
                                instance_type=instance_type)
        model.env['MMS_MAX_RESPONSE_SIZE'] = '20000000'
        model.env['accept_eula'] = 'true'

    # Use Sagemaker v2.174 or higher for usage with Llama
    # Also, no env can be passed for Llama
    elif ('llama-' in model_id):
        model = JumpStartModel(model_id=model_id, 
                                role=sagemaker_role,
                                region=aws_region,
                                instance_type=instance_type)
        # Does not accept env for marketplace
        # Error reported: 
        #   An error occurred (ValidationException) when calling the CreateModel operation: 
        #   Environment variable map cannot be specified when using a ModelPackage subscribed from AWS Marketplace.
    else:        
        model = Model(image_uri=container, 
                      model_data=model_url,
                      role=sagemaker_role,
                      region=aws_region,
                      instance_type=instance_type)
        model.env['MMS_MAX_RESPONSE_SIZE'] = '20000000'
    
    deploy(event, context, model, instance_type, endpoint_name)

def deploy_proprietary_model(event, context):    
    aws_region=os.environ['AWS_DEFAULT_REGION']
    aws_account_id = context.invoked_function_arn.split(":")[4]
    
    props = event['ResourceProperties']
    endpoint_name = props['EndpointName']
    model_id = props['ModelId']
    instance_type = props['InstanceType']
    sm_deployer_role_name = props['SMDeployerRole']
    
    # Role to give SageMaker permission to access AWS services.
    sagemaker_role= f'arn:aws:iam::{aws_account_id}:role/{sm_deployer_role_name}'
    

    # Specify an AWS container image. 
    model_package_arn = get_model_package_arn(model_id,instance_type,aws_region)
    
    print('model package arn: ', model_package_arn)

    model = ModelPackage( model_package_arn=model_package_arn,
                  role=sagemaker_role)
    
    deploy(event, context, model, instance_type, endpoint_name)

def delete_model(event, context):    
    aws_region=os.environ['AWS_DEFAULT_REGION']
    aws_account_id = context.invoked_function_arn.split(":")[4]
    
    #model_id = 'huggingface-text2text-flan-t5-xl' # event['model_id']
    #instance_type = 'ml.g5.2xlarge' # event['instance_type']
    
    props = event['ResourceProperties']
    endpoint_name = props['EndpointName']
    model_id = props['ModelId']
    instance_type = props['InstanceType']
    
    # Create a low-level SageMaker service client.
    sagemaker_client = boto3.client('sagemaker', region_name=aws_region)
    
    response = sagemaker_client.describe_endpoint_config(EndpointConfigName=endpoint_name)
    print('Endpoint config', response)
    
    # Get endpoint config
    # there is no EndpointConfigName
    # endpoint_config_name = response['ProductionVariants'][0]['EndpointConfigName']
    # structure:
    """
    Endpoint config {'EndpointConfigName': 'Test-FlanT5-22', 'EndpointConfigArn': 'arn:aws:sagemaker:us-east-1:xxxx:endpoint-config/test-flant5-22', 
         'ProductionVariants': [{'VariantName': 'AllTraffic', 'ModelName': 'sagemaker-jumpstart-2023-06-21-17-42-05-433', 'InitialInstanceCount': 1, 
         'InstanceType': 'ml.g5.2xlarge', 'InitialVariantWeight': 1.0}], 'CreationTime': datetime.datetime(2023, 6, 21, 17, 42, 7, 156000, tzinfo=tzlocal()), 
         'ResponseMetadata': {'RequestId': 'f10cb2b6-a2da-4360-b854-a207d718d9bd', 'HTTPStatusCode': 200, 'HTTPHeaders': {'x-amzn-requestid': 'f10cb2b6-a2da-4360-b854-a207d718d9bd',
         'content-type': 'application/x-amz-json-1.1', 'content-length': '358', 'date': 'Wed, 21 Jun 2023 18:08:42 GMT'}, 'RetryAttempts': 0}}
    """
    model_name = response['ProductionVariants'][0]['ModelName']
    print('Model name', model_name)
  
    # Delete model
    delete_model_response = sagemaker_client.delete_model(ModelName=model_name)

    # Delete endpoint configuration
    sagemaker_client.delete_endpoint_config(EndpointConfigName=endpoint_name)

    # Delete endpoint
    delete_endpoint_response = sagemaker_client.delete_endpoint(EndpointName=endpoint_name)
    
    response = {
        'Operation': 'Delete',
        'Status': '200',
        'Endpoint': endpoint_name,
        'PhysicalResourceId': generate_physical_resource_id(event, context),
        'EndpointDeletionResponse': delete_endpoint_response,
        'ModelDeletionResponse': delete_model_response
    }
    
    sendResponse(event, context, 'SUCCESS', response)

def sendResponse(event, context, responseStatus, responseData):
 
    responseBody = {
        'Status': responseStatus,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'PhysicalResourceId': generate_physical_resource_id(event, context),
        'Data': responseData
    }
 
    if ('FAILED' == responseStatus):
        responseBody['Reason'] = responseData
        del responseBody['Data']
        
    print("RESPONSE BODY:\n", responseBody)
 
    json_response_body = json.dumps(responseBody)
    print("SENDING RESPONSE.. {} to {} ".format(json_response_body, event['ResponseURL']))
    
    headers = {
        'content-type' : '',
        'content-length' : str(len(json_response_body))
    }

    try:
        http = urllib3.PoolManager()
        response = http.request('PUT', event['ResponseURL'], headers=headers, body=json_response_body)
        print("Status code:", response.status)

    except Exception as e:
        print("send(..) failed executing http.request(..):", e)

def lambda_handler(event, context):
    print('Incoming event: ', event)
    props = event['ResourceProperties']
    endpoint_name = props['EndpointName']

    try:
        if (event['RequestType'] == 'Create' or  event['RequestType'] == 'Update' ):
            if event['ResourceProperties']['ModelType'] == 'proprietary':
                return deploy_proprietary_model(event, context)
            else:    
                return deploy_opensoure_model(event, context)
        elif (event['RequestType'] == 'Delete'):
            return delete_model(event, context)

    except:
        error = sys.exc_info()
        print(error)
        errorMsg = error[1]
        print('Error in deploying or deleting model: ', errorMsg)

        response = {
            'Operation': event['RequestType'],
            'Status': '400',
            'Endpoint': endpoint_name,
            'ErrorMessage': str(errorMsg)
        }        
        sendResponse(event, context, 'FAILED', response)
