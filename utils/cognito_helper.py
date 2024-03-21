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
# Helper utility to handle cognito authentication/signup etc.

import os
import base64
import boto3
import botocore
import time
import json
import jwt
import requests
import base64
import hashlib
import hmac
import logging
import urllib.request
import urllib.parse
import streamlit as st
import extra_streamlit_components as stx
import pycognito
from pycognito import AWSSRP
from jose import jwk
from jose.utils import base64url_decode


DEFAULT_COGNITO_SCOPE='email+openid+phone+profile'

AWS_REGION=os.environ['AWS_DEFAULT_REGION']
CF_DISTRIBUTION = os.environ.get('CF_DISTRIBUTION')

POOL_ID = os.environ.get("POOL_ID")
POOL_DOMAIN_NAME = os.environ.get("POOL_DOMAIN_NAME")
APP_CLIENT_ID = os.environ.get("APP_CLIENT_ID")
APP_CLIENT_SECRET = os.environ.get("APP_CLIENT_SECRET")

COGNITO_KEY_URL = 'https://cognito-idp.{}.amazonaws.com/{}/.well-known/jwks.json'.format(AWS_REGION, POOL_ID)

FORMAT = '%(asctime)s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)
logger = logging.getLogger('gen-ai-invoker')

COGNITO_CUSTOM_READ_PROFILE = urllib.parse.quote(os.environ.get('COGNITO_CUSTOM_READ_PROFILE'), safe='', encoding=None, errors=None) 
COGNITO_CUSTOM_WRITE_PROFILE = urllib.parse.quote(os.environ.get('COGNITO_CUSTOM_WRITE_PROFILE'), safe='', encoding=None, errors=None) 
COGNITO_USERPOOL_CUSTOM_ATTRIBUTES_LIST=os.environ.get('COGNITO_USERPOOL_CUSTOM_ATTRIBUTES_LIST', '')

ALLOWED_EMAIL_DOMAINS = os.environ.get('ALLOWED_DOMAINS', 'amazon.com').split(',')

COUNTER = 1

APP_PAGE= f"https://{CF_DISTRIBUTION}"
signup_link = f"https://{POOL_DOMAIN_NAME}.auth.{AWS_REGION}.amazoncognito.com/signup?client_id={APP_CLIENT_ID}&response_type=code&redirect_uri={APP_PAGE}&scope={DEFAULT_COGNITO_SCOPE}+{COGNITO_CUSTOM_READ_PROFILE}+{COGNITO_CUSTOM_WRITE_PROFILE}"
login_link = f"https://{POOL_DOMAIN_NAME}.auth.{AWS_REGION}.amazoncognito.com/login?client_id={APP_CLIENT_ID}&response_type=code&redirect_uri={APP_PAGE}"
logout_link = f"https://{POOL_DOMAIN_NAME}.auth.{AWS_REGION}.amazoncognito.com/logout?client_id={APP_CLIENT_ID}&logout_uri={APP_PAGE}&redirect_uri={APP_PAGE}&response_type=code"

# States of form submission
CURRENT_USER_STATE_PROCEED2LOGIN = 1
CURRENT_USER_STATE_PROCEED2SIGNUP = 2
CURRENT_USER_STATE_PROCEED2LOGIN_AFTER_SIGNUP = 3
CURRENT_USER_STATE_SUBMIT_SIGNUP = 4
CURRENT_USER_STATE_SUBMIT_SIGNUP_TOKEN = 5
CURRENT_USER_STATE_VERIFY_SIGNUP= 6


with urllib.request.urlopen(COGNITO_KEY_URL) as f:
  response = f.read()
cognito_keys = json.loads(response.decode('utf-8'))['keys']

client = boto3.client( "cognito-idp", region_name=AWS_REGION )
cookie_manager = stx.CookieManager()

       
def to_camel_case(text):
    s = text.replace("-", " ").replace("_", " ").replace('.', ' ').replace(':', '.')
    s = s.split()
    if len(text) == 0:
        return text
    return ' '.join(i.capitalize() for i in s[0:])

def init_session_state():
    st.session_state["authenticated"] = None
    st.session_state["auth_code"] = None
    st.session_state["id_token"] = None
    st.session_state["access_token"] = None
    st.session_state["refresh_token"] = None

# Not using auth_code, 
# leaving it for future use
def get_auth_code():
    auth_query_params = st.experimental_get_query_params()
    try:
        auth_code = dict(auth_query_params)["code"][0]
    except (KeyError, TypeError):
        auth_code = ""
        
    return auth_code


def set_auth_code():
    init_session_state()
    auth_code = get_auth_code()
    st.session_state["auth_code"] = auth_code

# Not using user tokens
# for future reference - from https://github.com/MausamGaurav/Streamlit_Multipage_AWSCognito_User_Authentication_Authorization/blob/master/components/authenticate.py
def get_user_tokens(auth_code):

    cognito_token_url = f"https://{POOL_DOMAIN_NAME}.auth.{AWS_REGION}.amazoncognito.com/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = {
        "grant_type": "authorization_code",
        "client_id": APP_CLIENT_ID,
        "code": auth_code,
        "client_secret": APP_CLIENT_SECRET,
        "redirect_uri": 'https://' + CF_DISTRIBUTION,
    }

    token_response = requests.post(cognito_token_url, headers=headers, data=body)
    try:
        access_token = token_response.json()["access_token"]
        id_token = token_response.json()["id_token"]
    except (KeyError, TypeError) as e:
        access_token = ""
        id_token = ""

    return access_token, id_token

def get_user_info(access_token):
    userinfo_url = f"https://{POOL_DOMAIN_NAME}.auth.{AWS_REGION}.amazoncognito.com/oauth2/userInfo"
    
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {access_token}",
    }

    userinfo_response = requests.get(userinfo_url, headers=headers)
    return userinfo_response.json()


# Ref from - https://gist.github.com/GuillaumeDerval/b300af6d4f906f38a051351afab3b95c
def pad_base64(data):
    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += "=" * (4 - missing_padding)
    return data


def verify_signature(access_token):
    
    decoded_auth_header = jwt.get_unverified_header(access_token)
    decoded_kid = decoded_auth_header['kid']
    cognito_internal_kids = [ entry['kid'] for entry in cognito_keys ]
    if not decoded_auth_header['kid'] in cognito_internal_kids:
        return False

    # Using logic from https://github.com/awslabs/aws-support-tools/blob/master/Cognito/decode-verify-jwt/decode-verify-jwt.py for full signature verification
    # search for the kid in the downloaded public keys
    key_index = -1
    for i in range(len(cognito_keys)):
        if decoded_kid == cognito_keys[i]['kid']:
            key_index = i
            break
    if key_index == -1:
        logger.info('Public key not found in jwks.json')
        return False
        
    # construct the public key
    public_key = jwk.construct(cognito_keys[key_index])
    # get the last two sections of the token,
    # message and signature (encoded in base64)
    message, encoded_signature = str(access_token).rsplit('.', 1)
    # decode the signature
    decoded_signature = base64url_decode(encoded_signature.encode('utf-8'))
    # verify the signature
    if not public_key.verify(message.encode("utf8"), decoded_signature):
        logger.info('Signature verification failed')
        return False
    else:
        logger.info('Signature verification passed')
        return True
    
# Only checking for signature and access token expiration
def check_valid_access_token():

    access_token= st.session_state.get('access_token')
    if access_token is None or access_token == '':
        return False
    
    # Check if signature was already verified    
    signature_verified = st.session_state.get('signature_verified')
    if signature_verified is None:
        signature_verified = verify_signature(access_token)
        st.session_state['signature_verified'] = signature_verified        
        
    if not signature_verified:
        return signature_verified
    
    decoded_token = jwt.decode(access_token, algorithms = [ "RS256" ], options={"verify_signature": False})
    #logger.info('Decoded_Token: ' + decoded_token)
    return (time.time()  < decoded_token['exp'])                                                                                      

def copy_attributes_into_session_state(src_dict):
    st.session_state["authenticated"] = True
    st.session_state["access_token"] = src_dict.get('access_token')
    st.session_state["id_token"] = src_dict.get('id_token')
    st.session_state["refresh_token"] = src_dict.get('refresh_token')

def manage_session():
    # Check for expiration of existing access_token in session
    if st.session_state.get('authenticated') == True and st.session_state.get('access_token') is not None:
        valid_login = check_valid_access_token()
        if not valid_login:
            init_session_state()
        return
    
    # If we are going to store access_token newly into session,
    # skip expiration check
    
    found_access_token = False
    
    access_token = cookie_manager.cookies.get("access_token")
    get_all_cookie_from_session = st.session_state.get('get_all')
    init_cookie_from_session = st.session_state.get('init')
    
    if access_token is not None and access_token != "":
        
        copy_attributes_into_session_state(cookie_manager.cookies)
        found_access_token = True 
        
    elif get_all_cookie_from_session is not None:
        access_token_from_get_all = get_all_cookie_from_session.get('access_token')
        if access_token_from_get_all is not None and access_token_from_get_all != "":
            copy_attributes_into_session_state(get_all_cookie_from_session)
            found_access_token = True
        elif init_cookie_from_session is not None:
            access_token_from_init = init_cookie_from_session.get('access_token')
            if access_token_from_init is not None and access_token_from_init != "":
                copy_attributes_into_session_state(get_all_cookie_from_session)
                found_access_token = True
    
    if found_access_token:
        
        # Check for Access tokens & if already authenticated starting from session, then cookie manager
        valid_login = check_valid_access_token()
        if valid_login:
            return 

    # No tokens found from cookies or existing session, or token expired already
    # blank out everything
    init_session_state()

def reload_app():
    st.rerun()




def set_stage(stage):
    st.session_state.stage = stage
    
    if st.session_state["stage"] == CURRENT_USER_STATE_PROCEED2SIGNUP:
        return signup()

    if st.session_state["stage"] == CURRENT_USER_STATE_PROCEED2LOGIN:
        return login()
        
    if st.session_state["stage"] == CURRENT_USER_STATE_PROCEED2LOGIN_AFTER_SIGNUP:
        return post_login(st.session_state.username, st.session_state.password)

    if st.session_state["stage"] == CURRENT_USER_STATE_SUBMIT_SIGNUP_TOKEN:
        return confirm_signup()

    if st.session_state["stage"] == CURRENT_USER_STATE_VERIFY_SIGNUP:
        return post_confirm_signup(st.session_state.signup_username, st.session_state.confirm_code)

    elif st.session_state["stage"] == CURRENT_USER_STATE_SUBMIT_SIGNUP:
        
        extra_signup_attributes = {}
        for attrib in st.session_state:
            if attrib.startswith('custom:'):
                extra_signup_attributes[attrib] = st.session_state[attrib]
                    
        return post_signup(st.session_state.signup_username, st.session_state.signup_password, st.session_state.signup_email, st.session_state.signup_name,  extra_signup_attributes)
                
def post_login(username, password):
    global COUNTER
    aws_srp_args = {
        "client": client,
        "pool_id": POOL_ID,
        "client_id": APP_CLIENT_ID,
        "username": username,
        "password": password,
    }

    aws_srp_args["client_secret"] = APP_CLIENT_SECRET

    aws_srp = AWSSRP(**aws_srp_args)
    COUNTER += 1
    st.session_state.login_form_rendered = False
    
    try:
        tokens = aws_srp.authenticate_user()
        #logger.info('Auth Token on user authentication...' + str(tokens))

        auth_result = tokens["AuthenticationResult"]
        id_token = auth_result["IdToken"]
        access_token = auth_result["AccessToken"]
        refresh_token = auth_result["RefreshToken"]
        
        decoded_id_token = jwt.decode(id_token, algorithms = [ "RS256" ], options={"verify_signature": False})
        #logger.info('Decoded IdToken on user authentication...' + str(decoded_id_token))
        
        st.session_state["auth_username"] = username
        st.session_state["user_attrib:email"] = decoded_id_token['email']
        st.session_state["user_attrib:name"] = decoded_id_token['name']
        for key in decoded_id_token.keys():
            if 'custom:' in key:
                attrib = key.replace('custom', 'user_attrib')
                st.session_state[attrib] = decoded_id_token[key]
        
        cookie_manager.set("access_token", access_token, key="set_access_token-" + str(COUNTER))
        cookie_manager.set("refresh_token",  refresh_token, key="set_refresh_token-" + str(COUNTER))
        cookie_manager.set("id_token",  id_token, key="set_id_token-" + str(COUNTER))

        st.session_state['id_token'] = id_token
        st.session_state['authenticated'] = True
        st.session_state['access_token'] = access_token
        st.session_state['refresh_token'] =  refresh_token
        
        return True
        
    except botocore.exceptions.ClientError as error:
        logger.info("Error with Login: " + str(error))
        if error.response["Error"]["Code"] == "UserNotConfirmedException":
            logger.info("Login user not confirmed for: " + username)
            st.button("Confirm signup with confirmation code before proceeding with Login", on_click=set_stage, args=(CURRENT_USER_STATE_SUBMIT_SIGNUP_TOKEN,))
        else:
            logger.info('Login error response: ' + str(error))
            st.text('Login failed, incorrect username or password!!\n')

        st.button("Sign up as new user", on_click=set_stage, args=(CURRENT_USER_STATE_PROCEED2SIGNUP,))
        st.write('Back to [Login](/)')
        return False



def login():
    global COUNTER
    
    if st.session_state.stage != 1:
        return
    
    COUNTER += 1
    
    form_placeholder = st.empty()
    with form_placeholder:
        cols = st.columns([1, 3, 1])
        with cols[1]:
            with st.form("login_form-" + str(COUNTER)):
                st.subheader("Login")
                username = st.text_input("Username", key="username")
                password = st.text_input("Password", type="password", key="password")
                login_submitted = st.form_submit_button("Login", on_click=set_stage, args=(CURRENT_USER_STATE_PROCEED2LOGIN_AFTER_SIGNUP,))
    st.button("Proceed to Signup", on_click=set_stage, args=(CURRENT_USER_STATE_PROCEED2SIGNUP,))


# Ref: https://github.com/awsdocs/aws-doc-sdk-examples/blob/main/python/example_code/cognito/cognito_idp_actions.py
def secret_hash(username):
    key = APP_CLIENT_SECRET.encode()
    msg = bytes(username + APP_CLIENT_ID, "utf-8")
    secret_hash = base64.b64encode(
        hmac.new(key, msg, digestmod=hashlib.sha256).digest()
    ).decode()
    
    return secret_hash



def validate_email_domain(email_id):
    
    if '@' not in email_id:
        return False
        
    emailAddr = email_id.split('@')
    userEmailDomain = emailAddr[1]
    if userEmailDomain in ALLOWED_EMAIL_DOMAINS:
        return True
    
    return False
    
# Ref: https://docs.aws.amazon.com/code-library/latest/ug/cognito-identity-provider_example_cognito-identity-provider_SignUp_section.html
#      https://github.com/awsdocs/aws-doc-sdk-examples/blob/main/python/example_code/cognito/cognito_idp_actions.py#L56
def post_signup(username, password, email, name, extra_signup_attributes):
    global COUNTER
    
    if not validate_email_domain(email):
        logger.info(f'Error! Domain used for signup: {email} not allowed!!')
        st.text(f'Signup failed, email domain {email} not allowed!!')
        st.button("Retry registering again as new user", on_click=set_stage, args=(CURRENT_USER_STATE_PROCEED2SIGNUP,)) 
        return False
        
    kwargs = {
        "ClientId": APP_CLIENT_ID,
        "Username": username,
        "Password": password,
    }
    
    user_attributes = [ {"Name": "email", "Value": email }, {"Name": 'name', "Value": name } ]
    
    kwargs['SecretHash'] = secret_hash(username)
    for key in extra_signup_attributes.keys():
        user_attributes.append({ "Name": key, "Value": extra_signup_attributes[key] } )
    
    kwargs['UserAttributes'] = user_attributes
    st.session_state.login_form_rendered = False
    try:
        response = client.sign_up(**kwargs)
        logger.info('Signup response: ' + str(response))
        st.text('User signup done! Need to verify Signup through email confirmation')
        #st.button("Back to Login", on_click=set_stage, args=(CURRENT_USER_STATE_PROCEED2LOGIN,))
        st.button("Proceed to Confirm Signup", on_click=set_stage, args=(CURRENT_USER_STATE_SUBMIT_SIGNUP_TOKEN,))
        st.write('Back to [Login](/)')
        return True
        
    except Exception as e:
        print(e)
        logger.info('Error with signup: ' + str(e))
        st.text('Signup failed!!\n' + str(e))
        st.button("Retry registering as new user", on_click=set_stage, args=(CURRENT_USER_STATE_PROCEED2SIGNUP,)) 
        return False



def signup():
    global COUNTER
    if st.session_state.stage != 2:
        return
    
    COUNTER += 1
    form_placeholder = st.empty()
    extra_attributes = COGNITO_USERPOOL_CUSTOM_ATTRIBUTES_LIST.split(',')
    extra_signup_attributes = {}
    
    st.session_state.login_form_rendered = False
    
    with form_placeholder:
        cols = st.columns([1, 3, 1])
        with cols[1]:
            with st.form("signup_form-"+str(COUNTER)):
                st.subheader("Signup User")
                username = st.text_input("Username", key="signup_username")
                password = st.text_input("Password", type="password", key="signup_password")
                name = st.text_input("Name", key="signup_name")
                email = st.text_input("Email", key="signup_email")
                
                for extra_attrib in extra_attributes:
                    if extra_attrib != '':
                        val = st.text_input(to_camel_case(extra_attrib), key='custom:' + extra_attrib)
                        extra_signup_attributes[extra_attrib] = val
                    
                signup_submitted = st.form_submit_button("Signup", on_click=set_stage, args=(CURRENT_USER_STATE_SUBMIT_SIGNUP,))
            
    #st.write('Back to [Login Screen](/)')
    st.button("Confirm Signup", on_click=set_stage, args=(CURRENT_USER_STATE_SUBMIT_SIGNUP_TOKEN,))


    
def confirm_signup():
    global COUNTER
    if st.session_state.stage != CURRENT_USER_STATE_SUBMIT_SIGNUP_TOKEN:
        return
    
    COUNTER += 1
    form_placeholder = st.empty()
    
    with form_placeholder:
        cols = st.columns([1, 3, 1])
        with cols[1]:
            with st.form("confirm_signup_form-"+str(COUNTER)):
                st.subheader("Confirm Signup User")
                username = st.text_input("Username", key="signup_username")
                confirm_code = st.text_input("Confirmation Code", key="confirm_code")
                
                confirm_signup_submitted = st.form_submit_button("Confirm Signup", on_click=set_stage, args=(CURRENT_USER_STATE_VERIFY_SIGNUP,))
            
    st.write('Back to [Login Screen](/)')
    



def post_confirm_signup(signup_username, confirm_code):
    global COUNTER
    if st.session_state.stage != CURRENT_USER_STATE_VERIFY_SIGNUP:
        return
    
    kwargs = {
        "ClientId": APP_CLIENT_ID,
        "Username": signup_username,
        "ConfirmationCode": confirm_code,
        "ForceAliasCreation": True
    }
    
    kwargs['SecretHash'] = secret_hash(signup_username)
    
    try:
        response = client.confirm_sign_up(**kwargs)
        logger.info('Signup response: ' + str(response))
        st.text('User signup confirmation successfull! Proceed with Login')
        #st.button("Back to Login", on_click=set_stage, args=(1,))
        st.write('Back to [Login](/)')
        return True
        
    except Exception as e:
        logger.info('Error with signup confirmation:' + str(e))
        st.text('Signup confirmation failed!!\n' + str(e))
        st.button("Retry confirming signup again", on_click=set_stage, args=(CURRENT_USER_STATE_SUBMIT_SIGNUP_TOKEN,))
        st.button("Retry registering as new user", on_click=set_stage, args=(CURRENT_USER_STATE_PROCEED2SIGNUP,)) 
        return False
        
def logout():
    cookie_manager.delete('access_token', key="delete_access_token-" + str(COUNTER))
    cookie_manager.delete('refresh_token', key="delete_refresh_token-" + str(COUNTER))
    cookie_manager.delete('id_token', key="delete_id_token-" + str(COUNTER))
    init_session_state()
    st.session_state.stage = 1
    st.session_state.login_form_rendered = False
    st.write('Back to [Login](/)')
    login()
    
def getuser():
    return st.session_state.get("auth_username")

def get_welcome_msg():
    
    username = st.session_state.get("auth_username")
    
    email = st.session_state.get("user_attrib:email")
    name = st.session_state.get("user_attrib:name")
    
    custom_attrib_map = {}
    
    for key in st.session_state.keys():
        if 'user_attrib' in key and 'name' not in key:
            custom_attrib_map[ key.replace('user_attrib:', '') ] = st.session_state.get(key)
    
    '''
    # Dont display all profile info
    banner = f'Hello {name}, profile details: [ username: {username}'
    if len(custom_attrib_map) != 0:
        banner += f', {custom_attrib_map}'
    banner += "]" 
    '''
    banner = f'Hello {name}'
    return banner