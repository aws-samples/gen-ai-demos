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
import botocore, boto3, datetime
from botocore.session import get_session
import os


# 3600 seconds in an hour, this value should match your role's
# maximum session duration (AWS default is 1 hour). If you're
# role chaining (e.g. saml2aws) 1 hour is a hard limit.

assume_role_arn = os.getenv('IAM_ROLE') 

def refresh_external_credentials():
    """ Function to get temp creds for assumed role """
    sts_client = boto3.client('sts')
    response = sts_client.assume_role(
        RoleArn=assume_role_arn,
        RoleSessionName="session_name",
        DurationSeconds=3600
    )

    temp_credentials = response['Credentials']
    print(f"Assumed role {assume_role_arn} and got temporary credentials.")

    aws_access_key_id=temp_credentials['AccessKeyId']
    aws_secret_access_key=temp_credentials['SecretAccessKey']
    aws_session_token=temp_credentials['SessionToken']
    aws_expiry_time=temp_credentials.get('Expiration').isoformat()

    return {
        "access_key": aws_access_key_id,
        "secret_key": aws_secret_access_key,
        "token": aws_session_token,
        "expiry_time": aws_expiry_time
    }
    

def run_autorefresh_session():

    credentials = botocore.credentials.RefreshableCredentials.create_from_metadata(
        metadata=refresh_external_credentials(),
        refresh_using=refresh_external_credentials,
        method="sts-assume-role",
    )


    session = get_session()
    session._credentials = credentials
    session.set_config_variable("region", os.environ['AWS_DEFAULT_REGION'])
    autorefresh_session = boto3.session.Session(botocore_session=session)

    return autorefresh_session

    
