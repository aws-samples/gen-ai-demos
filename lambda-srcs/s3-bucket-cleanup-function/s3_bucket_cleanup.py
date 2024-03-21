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
import boto3

import requests

# Reference code from 
# https://gist.github.com/drumadrian/e1601ab34e7f609b5075f65599108960#file-custom-cloudformation-bucket-cleanup-yaml-L99-L103
def lambda_handler(event, context):

    try:
        bucketName = event['ResourceProperties']['BucketName']
        if event['RequestType'] == 'Delete':
            s3 = boto3.resource('s3')
            bucket = s3.Bucket(bucketName)
            for obj in bucket.objects.filter():
                s3.Object(bucket.name, obj.key).delete()
        sendResponse(event, context, "SUCCESS")
    except Exception as e:
        print(e)
        sendResponse(event, context, "FAILED")

def sendResponse(event, context, responseStatus):
    response_body = {'Status': responseStatus,
                   'Reason': 'Log stream name: ' + context.log_stream_name,
                   'PhysicalResourceId': context.log_stream_name,
                   'StackId': event['StackId'],
                   'RequestId': event['RequestId'],
                   'LogicalResourceId': event['LogicalResourceId'],
                   'Data': json.loads("{}")}
    requests.put(event['ResponseURL'], data=json.dumps(response_body))
      


