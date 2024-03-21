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

import os
import json
import boto3
import requests

'''
Parameters: 
    model_name - From list below or "list_foundation_models"
    prompt - Input to the model, string accepted, no default
    negative_prompt - Negative prompts to the model, no defaults
    task - should be ttoi (Text to Image) or itoi (Image to Image)
    style_preset - Style of image to generate

Models currently supported:
    stability.stable-diffusion-xl

Notes:
    I needed to add a bedrock VPC endpoint to avoid timeouts.
    Some endpoints take 10-15 seconds to respond, set lambda timeout accordingly.
    Expects an environment variable called "secret_name".  This is a Secrets Manager
        secret that contains AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION
        If your setup calls bedrock locally, make sure your Lambda permissions include bedrock access
        and remove the cross-account settings in the bedrock client calls.
    Youll need a layer for requests and one for the private version of boto3 that includes bedrock.
        https://towardsdatascience.com/building-custom-layers-on-aws-lambda-35d17bd9abbb
    Input images should be sent in base64 format
    Responses will also be in base64 format.
        Example to decode: 
            Image.open(io.BytesIO(base64.decodebytes(bytes(image_2_b64_str, "utf-8"))))

Working On:
    Better error handling, logging, and status responses
    Cohere (when its available)
'''

secret_name = os.environ['secret_name']


def call_list_models():

    aws_access_key, aws_secret_access, region = get_secrets()
    bedrock = boto3.client('bedrock',region_name=region, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_access) 

    model_list = bedrock.list_foundation_models()
    response = []
    for model in model_list['modelSummaries']:
        print(model['modelId'])
        response.append(model['modelId'])
    
    return response


def call_bedrock_sd(task, prompt, model_name="stability.stable-diffusion-xl", negative_prompts="poorly rendered", style_preset="photographic", init_image=None):

    aws_access_key, aws_secret_access, region = get_secrets()
    bedrock = boto3.client('bedrock',region_name=region, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_access) 

    if task == "ttoi":

        request = json.dumps({
            "text_prompts": (
                [{"text": prompt, "weight": 1.0}]
                + [{"text": negprompt, "weight": -1.0} for negprompt in negative_prompts]
            ),
            "cfg_scale": 5,
            "seed": 5450,
            "steps": 70,
            "style_preset": style_preset,
        })

        response = bedrock.invoke_model(body=request, modelId=model_name)
        response_body = json.loads(response.get("body").read())

        return response_body["artifacts"][0].get("base64")
    
    elif task == "itoi":
        request = json.dumps({
            "text_prompts": (
                [{"text": prompt, "weight": 1.0}]
                + [{"text": negprompt, "weight": -1.0} for negprompt in negative_prompts]
            ),
    "cfg_scale": 10,
    "init_image": init_image,
    "seed": 321,
    "start_schedule": 0.6,
    "steps": 50,
    "style_preset": style_preset,
    })

    response = bedrock.invoke_model(body=request, modelId=model_name)
    response_body = json.loads(response.get("body").read())

    return response_body["artifacts"][0].get("base64")


def get_secrets():
    headers = {"X-Aws-Parameters-Secrets-Token": os.environ.get('AWS_SESSION_TOKEN')}
    secrets_extension_http_port = "2773"

    secrets_extension_endpoint = "http://localhost:" + \
    secrets_extension_http_port + \
    "/secretsmanager/get?secretId=" + \
    secret_name
  
    r = requests.get(secrets_extension_endpoint, headers=headers)
  
    secret = json.loads(r.text)["SecretString"]
    aws_access_key = json.loads(secret)["AWS_ACCESS_KEY_ID"]
    aws_secret_access = json.loads(secret)["AWS_SECRET_ACCESS_KEY"]
    region = json.loads(secret)["AWS_DEFAULT_REGION"]
    
    return aws_access_key, aws_secret_access, region
    
