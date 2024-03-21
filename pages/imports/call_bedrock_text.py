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
    max_tokens - Configures the maximum number of tokens in the generated response
    temperature - 0-1, highest probability (least creative) to lowest probability (most creative)
    top_p - defines a cut off based on the sum of probabilities of the potential choices.
    top_k - Top K defines the cut off where the model no longer selects the words

Models currently supported:
    amazon.titan-tg1-large
    ai21.j2-grande-instruct
    ai21.j2-jumbo-instruct
    anthropic.claude-instant-v1
    anthropic.claude-v1
    anthropic.claude-v1-100k
    anthropic.claude-v2
    anthropic.claude-v2-100k

Notes:
    I needed to add a bedrock VPC endpoint to avoid timeouts.
    Some endpoints take 10-15 seconds to respond, set lambda timeout accordingly.
    Expects an environment variable called "secret_name".  This is a Secrets Manager
        secret that contains AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION
        If your setup calls bedrock locally, make sure your Lambda permissions include bedrock access
        and remove the cross-account settings in the bedrock client calls.
    Youll need a layer for requests and one for the private version of boto3 that includes bedrock.
        https://towardsdatascience.com/building-custom-layers-on-aws-lambda-35d17bd9abbb

Working On:
    Better error handling, logging, and status responses
    Cohere (when its available)
'''

key = os.environ['AWS_ACCESS_KEY_ID']
secret = os.environ['AWS_SECRET_ACCESS_KEY']
region = os.environ['AWS_DEFAULT_REGION']


def call_list_models():

    bedrock = boto3.client('bedrock',region_name=region, aws_access_key_id=key, aws_secret_access_key=secret) 

    model_list = bedrock.list_foundation_models()
    response = []
    for model in model_list['modelSummaries']:
        print(model['modelId'])
        response.append(model['modelId'])
    
    return response


def call_bedrock_titan(model_name, prompt_text, max_token_count=512, temperature=1, top_p=1, stop_sequences=[]):

    bedrock = boto3.client('bedrock',region_name=region, aws_access_key_id=key, aws_secret_access_key=secret) 

    body = json.dumps({
        "inputText": prompt_text
        })

    response = bedrock.invoke_model(
        body=body, 
        modelId=model_name, 
        accept="application/json", 
        contentType="application/json"
    )
        
    response_body = json.loads(response.get("body").read())
    return response_body.get("results")[0].get("outputText")


def call_bedrock_anthropic(model_name, prompt_text, max_tokens=300, temperature=0.5, top_k=250, top_p=1):
    
    bedrock = boto3.client('bedrock',region_name=region, aws_access_key_id=key, aws_secret_access_key=secret) 

    body = json.dumps({
        "prompt": prompt_text, 
        "max_tokens_to_sample": int(max_tokens),
        "temperature": float(temperature),
        "top_k": int(top_k),
        "top_p": float(top_p)
        })
        
    response = bedrock.invoke_model(
        body=body, 
        modelId=model_name, 
        accept="application/json", 
        contentType="application/json"
    )
            
    response_body = json.loads(response.get("body").read())    
    
    return response_body.get("completion")


def call_bedrock_jurassic(model_name, prompt_text, max_tokens=200, temperature=0.5, top_p=0.5):

    bedrock = boto3.client('bedrock',region_name=region, aws_access_key_id=key, aws_secret_access_key=secret) 

    body = json.dumps({
        "prompt": prompt_text, 
        "maxTokens": int(max_tokens)
    })

    response = bedrock.invoke_model(
        body=body, 
        modelId=model_name, 
        accept="application/json", 
        contentType="application/json"
    )
    
    response_body = json.loads(response.get("body").read())

    return response_body.get("completions")[0].get("data").get("text")
