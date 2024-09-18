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
# Helper utility to switch beteween diff models and encapsulate the model invocations, parameter handling
import os
import boto3
import botocore
import json
import anthropic
import ai21
import time
import logging
import pages.imports.sts_assume_role as boto3_session
import csv
import collections
import streamlit as st

autorefresh_session = boto3_session.run_autorefresh_session()

FORMAT = '%(asctime)s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)
logger = logging.getLogger('gen-ai-invoker')
client = boto3.client('runtime.sagemaker')

MODEL_FAMILY = [ 'JUMPSTART', 'BEDROCK' ]
MODEL_FAMILY_JUMPSTART = 0
MODEL_FAMILY_BEDROCK = 1

key = os.environ['AWS_ACCESS_KEY_ID']
secret = os.environ['AWS_SECRET_ACCESS_KEY']
region = os.environ['AWS_DEFAULT_REGION']
BEDROCK_TITAN_PAYLOAD_LIMIT = (int)(os.getenv('BEDROCK_TITAN_PAYLOAD_LIMIT', '20000'))

bedrock = autorefresh_session.client('bedrock')
bedrockruntime = autorefresh_session.client('bedrock-runtime')
sagemaker = autorefresh_session.client('runtime.sagemaker')
bedrock_models = None

jumpstart_endpoint = None
jumpstart_detection_passed = None

bedrock_text_provider_map = {}
bedrock_img_provider_map = {}
bedrock_embedding_provider_map = {}

genai_models = []
genai_model_entries= {}
genai_model_functions = {}

MAX_RECENT_RUNS = 5
recent_cost_stats = collections.deque(MAX_RECENT_RUNS*[ {}], MAX_RECENT_RUNS)


LLM_PRICING = './utils/llm_pricing.csv'
AUTO_GENERATED_PROMPT = 'Generate three prompts'

def add_cost_entry(total_cost, model_id, input_tokens, output_tokens, user_generated_prompt ):
    report_cost_entry = { 
                            'cost': f'{total_cost:.6f}', 
                            'model_id': model_id, 
                            'input': str(input_tokens), 
                            'output': str(output_tokens),
                            'user_generated': user_generated_prompt
                        }
    recent_cost_stats.append(report_cost_entry)
    
    
    
def report_cost():
    
    total_cost = st.session_state.get('total_running_cost')
    if total_cost is None or total_cost == 0:
        return ''
    
    recent_cost_entries = ''
    reverse_list = reversed(recent_cost_stats)
    
    for entry in reverse_list:
        if not entry:
            continue
        
        
        #recent_cost_entries = recent_cost_entries + '  \n\n' if recent_cost_entries != '' else ''
        recent_cost_entries += f"  \n\n Invoke cost: ${entry['cost']}, model: {entry['model_id']}, input tokens: {entry['input']}," + f" output tokens: {entry['output']}, user-generated-prompt: {entry['user_generated']}"
        
    return f'Estimated cost of recent runs: ${total_cost}  \n\n Breakdown:  \n\n {recent_cost_entries}'    
    
def load_llm_pricing():
    global region
    llm_price_dict = {}
    with open(LLM_PRICING, 'r') as llm_pricing:
        reader = csv.DictReader(llm_pricing)
        for row in reader:
            if row['region'] == 'all':
                llm_price_dict[row['model_id']] = row
            elif row['region'] in region:
                llm_price_dict[row['model_id']] = row
    
    print(llm_price_dict)            
    return llm_price_dict
    
    
LLM_COST_DATA = load_llm_pricing()

def find_matching_entry(model_id):
    for key in LLM_COST_DATA:
        if key in model_id:
            return LLM_COST_DATA[key]
    
    return None

def save_cost_entry_for_model( model_id, input_body, output_body):
    
    input_tokens =int(len(input_body)/4) + 1 
    output_tokens =int(len(output_body)/4) + 1 

    user_generated_prompt = True if (AUTO_GENERATED_PROMPT not in input_body) else False
    save_cost_entry_for_model_tokens( model_id, input_tokens, output_tokens, user_generated_prompt)


def save_cost_entry_for_model_tokens( model_id, input_tokens, output_tokens, user_generated_prompt):

    llm_price_entry = LLM_COST_DATA.get(model_id)
    if llm_price_entry is None:
        llm_price_entry = find_matching_entry(model_id)
    
    if llm_price_entry is None:
        return
    
    input_token_cost = llm_price_entry['input_token_price']
    output_token_cost = llm_price_entry['output_token_price']
    
    total_cost = input_tokens*float(input_token_cost)/1000 + output_tokens*float(output_token_cost)/1000
    cost_entry = f'Invoke cost: ${total_cost:.8f}, model: {llm_price_entry["model_id"]}, input tokens: {input_tokens}, output tokens: {output_tokens}'
    current_cost = f'{cost_entry}, user-generated-prompt: {user_generated_prompt}'
    
    logger.info(f'Invocation Cost : {cost_entry}')
     
    add_cost_entry(total_cost, model_id, input_tokens, output_tokens, user_generated_prompt )
    
    # Check session state for previously saved invocation costs
    # Add current costs to prev states.
    #prev_costs = st.session_state.get('invoke_cost_summary')
    #st.session_state['invoke_cost_summary'] =  current_cost if prev_costs is None else current_cost  + '\n\n' + prev_costs
    prev_total_costs = st.session_state.get('total_running_cost')
    new_total_cost = total_cost 
    if prev_total_costs is not None: 
        new_total_cost += float(prev_total_costs)
    new_total_cost_str = f'{new_total_cost:.8f}'
    st.session_state['total_running_cost'] = new_total_cost_str


def create_model_function_mapping():
    global genai_models, genai_model_entries
    
    has_bedrock_access()
    for provider in bedrock_text_provider_map.keys():
        
        # Ignore Cohere for this v1 release
        if provider == 'Cohere':
            logger.info(f'Not considering Provider: {provider} for v1 release........')
            continue
        
        model_list = bedrock_text_provider_map[provider]
        if len(model_list) <= 2:
            for modelId in model_list:
                entry = model_list[modelId]
                modelName = entry['modelName']
                genai_models.append(modelName) 
                genai_model_entries[modelName] = modelId
        else:
            
            for modelId in model_list:
                entry = model_list[modelId]
                
                addEntry = False
                modelName = entry['modelName']
                
                if (provider == 'Amazon'):
                    if 'titan-text-lite-v1' in modelId or 'titan-text-express-v1' in modelId:
                        addEntry = True
                elif (provider == 'Anthropic'):
                    if ('claude-3' in modelId) or ('claude-v2:1' in modelId) or  ('claude-instant-v1' in modelId) :
                        addEntry = True
                        modelName = to_camel_case(modelId)
                elif (provider == 'Meta'):
                    if ('lama2-13b-chat-v1' in modelId) or  ('lama2-70b-chat-v1' in modelId) :
                        addEntry = True
                elif (provider == 'AI21 Labs'):
                    if ('ai21.j2-ultra-v1' in modelId) :
                        addEntry = True
                          
                else:
                    logger.info('Not considering model: {}........'.format(entry))
                    
                if addEntry:
                    genai_models.append(modelName) 
                    genai_model_entries[modelName] = modelId
        
    

    

def find_matching_model_id_by_type(model_type_prefix, model_type_list, model_id_list):
    index = 0
    size = len(model_type_list)
    while (index < size):
        if model_type_prefix == model_type_list[index]:
            return model_id_list[index]
        index +=1
    
    err = f"Unable to find matching model type for given model type:{model_type_prefix}" 
    logger.error(err)
    raise Exception(err)
    


    
    
def has_jumpstart_deployed():
    global jumpstart_endpoint
    global jumpstart_detection_passed
    
    if jumpstart_detection_passed is not None:
        return jumpstart_detection_passed
    
    logger.debug('Checking if jumpstart endpoint was defined and deployed??')
    jumpstart_endpoint = os.environ.get('JUMPSTART_MODEL_ENDPOINT')
    logger.info('Jumpstart endpoint from env: {}'.format(jumpstart_endpoint))
    if jumpstart_endpoint == None or jumpstart_endpoint == 'None' or jumpstart_endpoint == '':
        jumpstart_detection_passed = False
        err = 'Jumpstart Endpoint not defined, detection failed!'
        logger.warning(err)
        return jumpstart_detection_passed
        
    try:
        #print(client)
        
        payload = {
            "inputs": 'Test data'
            }
        
        response = client.invoke_endpoint(EndpointName=jumpstart_endpoint, 
                                            ContentType='application/json', 
                                            Body=json.dumps(payload).encode('utf-8'),
                                            CustomAttributes='accept_eula=true')
        #print(response)
        jumpstart_detection_passed = True
        return jumpstart_detection_passed

    except botocore.exceptions.ClientError as e1:
        errorMsg = str(e1)
        #logger.exception(e1)
        logger.error('Got error in accessing Jumpstart endpoint: {}'.format(errorMsg))
        jumpstart_detection_passed = True if ('/aws/sagemaker/Endpoints' in errorMsg) else False
        if jumpstart_detection_passed:
            logger.info('Ignoring prev error as it indicates the endpoint is setup')
        logger.info('Jumpstart Detection Passed?: {}'.format(jumpstart_detection_passed))
        return jumpstart_detection_passed
    
def has_bedrock_access():
    global bedrock_models
    global bedrock_text_provider_map, bedrock_img_provider_map, bedrock_embedding_provider_map
    logger.info('Checking Bedrock access')

    
    try:
        response = bedrock.list_foundation_models()
        #logger.info('List foundation models: {}'.format(response))
        
        model_summaries = response['modelSummaries']
        
        for summary in model_summaries:
            provider = summary['providerName']
            modality = summary['outputModalities'][0]
            
            #print('Provider: ', provider)
            if modality == 'TEXT':
                bedrock_provider_map = bedrock_text_provider_map
            elif modality == 'IMAGE':
                bedrock_provider_map = bedrock_img_provider_map
            elif modality == 'EMBEDDING':
                bedrock_provider_map = bedrock_embedding_provider_map
            
            model_list = bedrock_provider_map.get(provider)
            if model_list == None:
                model_list = {}
            
            # Only add those that support on-demand for our demo app
            if 'ON_DEMAND' in summary['inferenceTypesSupported']:
                model_list[summary['modelId']] = summary
            bedrock_provider_map[provider] = model_list
        
            
    
        # logger.info('Bedrock Text models List: {}'.format(bedrock_text_provider_map))
        # logger.info('Bedrock Img models List: {}'.format(bedrock_img_provider_map))
        # logger.info('Bedrock Embedding models List: {}'.format(bedrock_embedding_provider_map))
        # logger.debug('Bedrock models raw response: {}'.format(response))
        
        #response_lines = response['body'].readlines()
        #print(response_lines)
    except botocore.exceptions.ClientError as e1:
        errorMsg = str(e1)
        logger.exception(e1)
        #if 'AccessDenied' in errorMsg:
        return False
        
    return True


def check_preference():
    preference = MODEL_FAMILY[MODEL_FAMILY_BEDROCK]
    
    bedrock_models_env = os.getenv('BEDROCK_MODEL_TYPES')
    bedrock_model_ids_env = os.getenv('BEDROCK_MODEL_IDS')
    
    jumpstart_models_env = os.getenv('JUMPSTART_MODEL_TYPES')
    jumpstart_model_ids_env = os.getenv('JUMPSTART_MODEL_IDS')
    
    preference = os.getenv('PREFER_MODEL_FAMILY')


    logger.info('Has Jumpstart deployed!!: {}'.format(has_jumpstart))
    logger.info('Has Bedrock access!!: {}'.format(has_bedrock))
    
    if not (has_bedrock or has_jumpstart):
        preference = 'Failed both options for Sagemaker!! Jumpstart not deployed and no access to Bedrock!!'
        logger.info(preference)
        return preference
        
    logger.info('Given Model preference: {}'.format(preference))
    if (preference == MODEL_FAMILY[MODEL_FAMILY_BEDROCK]):
        if (not has_bedrock):
            logger.info('Defaulting to Jumpstart as there is no access to Bedrock!!')
            preference = MODEL_FAMILY[MODEL_FAMILY_JUMPSTART]
    else:
        if (not has_jumpstart ):
            logger.info('Defaulting to Bedrock as there is no jumpstart deployed, even as Jumpstart was preferred!!')
            preference = MODEL_FAMILY[MODEL_FAMILY_BEDROCK]

    return preference

has_bedrock = has_bedrock_access()
has_jumpstart = has_jumpstart_deployed()
env_model_preference = check_preference()

def get_bedrock_models_access():
    global bedrock_models
    
    if not has_bedrock:
        return None
    
    if bedrock_models is None:
        has_bedrock_access()
        
    return bedrock_models
    
def get_model(model_name):
    if (has_bedrock):
        model_function = find_bedrock_model(model_name)
        if model_function is None:
            err = 'Unable to find matching bedrock model!!'
            logger.error(err)
            raise Exception(err)
        else:
            return model_function
    
    if (has_jumpstart):
        model_function = find_jumpstart_model(model_name)
        if model_function is None:
            err = 'Unable to find matching jumpstart model!!'
            logger.error(err)
            raise Exception(err)
        else:
            return model_function

    finalErr = 'Failed both options for Sagemaker!! Jumpstart not deployed and no access to Bedrock!!'
    logger.error(finalErr)
    raise Exception(finalErr)


def get_jumpstart_model():
    
    if not has_jumpstart and has_bedrock and env_model_preference == 'BEDROCK':
        # Go with default Bedrock Claude
        return find_bedrock_model('claude-v2')
        
    jumpstart_model_name = os.environ.get('PREFERRED_JUMPSTART_MODEL_TYPE')
    jumpstart_model_id = os.environ.get('PREFERRED_JUMPSTART_MODEL_ID')
    
    return find_jumpstart_model(jumpstart_model_name)
    
def find_jumpstart_model(model_name):
    if model_name.lower().startswith('bedrock'):
        raise Exception('Searching for Jumpstart Models against Bedrock!!')
    
    if not has_jumpstart:
        raise Exception('Jumpstart Endpoint not defined!!')
    
    call_models = [
            {
                'func': call_hf_falcon_model,
                'model_id': 'falcon',
                'label': 'Huggingface Falcon',
                'char_limits':10000
            },
            {
                'func': call_flan_t5_model,
                'model_id': 'flan-t5',
                'label': 'Flan T5',
                'char_limits':5000
            },
            {
                'func': call_jumpstart_ai21_j2_ultra_model,
                'model_id': 'j2-ultra',
                'label': 'AI21 Jurassic2 Ultra',
                'char_limits':5000
            },
            {
                'func': call_jumpstart_ai21_j2_mid_model,
                'model_id': 'j2-mid',
                'label': 'AI21 Jurassic2 Grande',
                'char_limits':5000
            },
            {
                'func': call_llama_2_13b,
                'model_id': 'llama-2-13b-chat',
                'label': 'SageMaker Meta Llama-2-13b-chat',
                'char_limits':5000
            },
            {
                'func': call_llama_2_70b,
                'model_id': 'llama-2-70b-chat',
                'label': 'SageMaker Meta Llama-2-70b-chat',
                'char_limits':5000
            },
            {
                'func': call_sdxl_model,
                'model_id': 'stable-diffusion',
                'label': 'StableDiffusion SDXL'
            }
        ] 
    
    for call_model in call_models:
        if call_model['model_id'] in model_name.lower():
            return call_model
            
    logger.error('Error!! Unable to find any matching jumpstart models')
    return None

def call_llama_2_7b_f(query, max_new_tokens=512, temperature = 0.6, top_p = 0.9):
    logger.info('Invoking llama-2-7b-f')
    model_type = 'Meta TextGeneration Llama-2-7b-f'
    qa_prompt = f'Question: {query}\nAnswer:'
    inputs_json = [[{"role": "user", "content": qa_prompt}]] 
    #inputs_str = json.dumps(inputs_json)
    #payload = {"inputs": json.dumps(inputs_json), "parameters": {"max_new_tokens": max_new_tokens, "top_p": top_p, "temperature": temperature}}
    payload = {"inputs": inputs_json, "parameters": {"max_new_tokens": max_new_tokens, "top_p": top_p, "temperature": temperature}}
    response = client.invoke_endpoint( EndpointName=jumpstart_endpoint, ContentType="application/json", Body=json.dumps(payload).encode('utf-8'), CustomAttributes="accept_eula=true" )
    
    responseBody = response['Body'].read()
    json_obj = json.loads(responseBody)
    result_text = json_obj[0]['generation']['content']

    # Strip off additional quotes as it breaks the model with subsequent calls
    return result_text.strip('\"')

   
def call_llama_2_13b(query, max_new_tokens=512, temperature = 0.6, top_p = 0.9):
    
    return call_llama_2_code_response(query, 'SageMaker Meta Llama-2-13b-chat', max_new_tokens, temperature, top_p)
    

def call_llama_2_70b(query, max_new_tokens=512, temperature = 0.6, top_p = 0.9):
    
    return call_llama_2_code_response(query, 'SageMaker Meta Llama-2-70b-chat', max_new_tokens, temperature, top_p)


def call_llama_2_code_response(query, model_id, max_new_tokens, temperature, top_p):
    
    #qa_prompt = f'Context: {passage}\nQuestion: {prompt}\nAnswer:'
    qa_prompt = f'Question: {query}\nAnswer:'
    inputs_json = [[{"role": "user", "content": qa_prompt}]] 
    inputs_str = json.dumps(inputs_json)
    #payload = {"inputs": json.dumps(query_template), "parameters": {"max_new_tokens": max_new_tokens, "top_p": top_p, "temperature": temperature}}
    payload = {"inputs": inputs_json, "parameters": {"max_new_tokens": max_new_tokens, "top_p": top_p, "temperature": temperature}}
    
    logger.info('Invoking Llama-2 ... model: {}'.format(model_id))
    #logger.debug('Llama Incoming payload: {}', payload)
    
    
    response = client.invoke_endpoint( EndpointName=jumpstart_endpoint, ContentType="application/json", Body=json.dumps(payload).encode('utf-8'), CustomAttributes="accept_eula=true" )
    responseBody = response['Body'].read()

    json_obj = json.loads(responseBody)
    result_text = json_obj[0]['generated_text']

    #logger.debug('Llama payload: {} \n------- and associated response: {}'.format(body_string, result_text))

    # Strip off additional quotes as it breaks the model with subsequent calls
    return result_text.strip('\"')

            
def call_hf_falcon_model(query, max_new_tokens=1024, return_full_text=True, do_sample = True, temperature = 0.5, repetition_penalty = 1.03, top_p = 0.9, top_k = 1):
    model_id = 'hf-llm-falcon-7b-instruct-bf16' 
    model_type = 'falcon'
    
    logger.info('Invoking HuggingFace Falcon ... model: {}'.format(model_id))
    payload = {
    "inputs": query,
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "return_full_text": return_full_text,
            "do_sample": do_sample,
            "temperature": temperature,
            "repetition_penalty": repetition_penalty,
            "top_p": top_p,
            "top_k": top_k,
            "stop": ["<|endoftext|>", "</s>"]
        }
    }
    #print('Payload for falcon', payload)
    response = client.invoke_endpoint(EndpointName=jumpstart_endpoint, ContentType='application/json', Body=json.dumps(payload).encode('utf-8'))
    model_predictions = json.loads(response['Body'].read())
    resp = str(model_predictions[0]['generated_text'][len(query):])
    return resp


def call_flan_t5_model(query, max_length=512, top_k = 1):
    
    model_id = 'flan-t5-xl'
    model_type = 'flan-t5'
    
    logger.info('Invoking HuggingFace Falcon ... model: {}'.format(model_id))
    jumpstart_endpoint = os.environ.get('JUMPSTART_MODEL_ENDPOINT')
    if jumpstart_endpoint == None:
        raise Exception('Jumpstart Endpoint not defined!!')
        
    payload = {
    "text_inputs": query,
        "parameters": {
            "max_length": max_length,
            "top_k": top_k
        }
    }
    response = client.invoke_endpoint(EndpointName=jumpstart_endpoint, ContentType='application/json', Body=json.dumps(payload).encode('utf-8'))
    model_predictions = json.loads(response['Body'].read())
    resp = str(model_predictions[0]['generated_text'][len(query):])
    return resp

def call_jumpstart_ai21_j2_ultra_model(prompt_text, max_tokens = 500, temperature = 1, top_p = 1, top_k = 250, stop_sequences = [],  countPenalty = 0, presencePenalty = 0, frequencyPenalty = 0):
    model_id = 'ai21.j2-ultra'
    model_type = 'AI21 Labs Jurassic2 Ultra'
    return call_jumpstart_ai21_j2_model(model_id, model_type, prompt_text,max_tokens, temperature, top_p, top_k, stop_sequences, countPenalty, presencePenalty, frequencyPenalty)

def call_jumpstart_ai21_j2_mid_model(prompt_text, max_tokens = 500, temperature = 1, top_p = 1, top_k = 250, stop_sequences = [],  countPenalty = 0, presencePenalty = 0, frequencyPenalty = 0):
    model_id = 'ai21.j2-mid'
    model_type = 'AI21 Labs Jurassic2 Mid'  
    return call_jumpstart_ai21_j2_model(model_id, model_type, prompt_text,max_tokens, temperature, top_p, top_k, stop_sequences, countPenalty, presencePenalty, frequencyPenalty)


def call_jumpstart_ai21_j2_model(model_id, model_type, query, max_length=512, top_k = 1):
    
    logger.info('Invoking AI21 Jurassic2, model: {}'.format(model_id))
    jumpstart_endpoint = os.environ.get('JUMPSTART_MODEL_ENDPOINT')
    if jumpstart_endpoint == None:
        err = 'Jumpstart Endpoint not defined!!'
        logger.exception(err)
        raise Exception(err)

    presence_penalty = {}
    count_penalty = {}
    frequency_penalty = {}
    presence_penalty['scale'] = '5.0'
    count_penalty['scale'] = '2.0'
    frequency_penalty['scale'] = '42.7'
    response = ai21.Completion.execute(sm_endpoint=jumpstart_endpoint,
                prompt=query,
                minTokens=tokens,
                maxTokens=max_length,
                temperature=temp,
                presencePenalty=presence_penalty,
                countPenalty=count_penalty,
                frequencyPenalty=frequency_penalty,
                numResults=1,
                topP=1,
                topKReturn=0,
                stopSequences=["##"])

    resp = response['completions'][0]['data']['text']
    #print("response from J2 is:" + str(resp))
    return resp

def call_sdxl_model(prompt_text, style_preset='digital-art',height=512, width=512, image_strength=0.5,cfg_scale=10,seed=1885337276,steps=100):
    model_id = 'stability.stable-diffusion-xl-v1'
    model_type = 'sd.sdxl'
    
    logger.info('Call_Model on Jumpstart stable-diffusion...model: {}'.format(model_id))
    payload = { "text_prompts": [ 
                                { "text": prompt_text} 
                    ] ,
                    "cfg_scale": cfg_scale,
                    "height": height,
                    "width": width,
                    "image_strength": image_strength,
                    "style_preset": style_preset,
                    "seed": seed,
                    "steps": steps
                }
    
    response = client.invoke_endpoint(EndpointName=jumpstart_endpoint, ContentType='application/json', Body=json.dumps(payload).encode('utf-8'))
    model_predictions = json.loads(response['Body'].read())
    resp = str(model_predictions[0]['generated_text'][len(query):])
    return resp
        

def find_bedrock_model(model_id):
    
    call_models = [
            {
                'func': call_bedrock_titan_text_lite_model,
                'model_id': 'titan-text-lite',
                'label': 'Bedrock Titan Text Lite',
                'char_limits':4000
            },
            {
                'func': call_bedrock_titan_text_express_model,
                'model_id': 'titan-text-express',
                'label': 'Bedrock Titan Text Express',
                'char_limits':4000
            },
            {
                'func': call_bedrock_titan_embedding_text_model,
                'model_id': 'titan-embedding-text',
                'label': 'Bedrock Titan Embedding Text',
                'char_limits':4000
            },
            {
                'func': call_bedrock_claude_model_v3,
                'model_id': 'bedrock claude-v3-sonnet',
                'label': 'Anthropic Claude v3 Sonnet',
                'char_limits':20000
            },
            {
                'func': call_bedrock_claude_model_v2_1,
                'model_id': 'claude-v2:1',
                'label': 'Anthropic Claude v2.1',
                'char_limits':15000
            },
            {
                'func': call_bedrock_claude_model_instant_v1,
                'model_id': 'claude-instant-v1',
                'label': 'Anthropic Claude Instant v1',
                'char_limits':10000
            },
            {
                'func': call_bedrock_claude_model_v1,
                'model_id': 'claude-v1',
                'label': 'Anthropic Claude v1',
                'char_limits':10000
            },
            {
                'func': call_bedrock_claude_v1_100k,
                'model_id': 'claude-v1-100k',
                'label': 'Anthropic Claude v1 100K',
                'char_limits':50000
            },
            {
                'func': call_bedrock_claude_v2_100k,
                'model_id': 'claude-v2-100k',
                'label': 'Anthropic Claude v2 100K',
                'char_limits':50000
            },
            {
                'func': call_bedrock_claude_model_v2,
                'model_id': 'claude-v2',
                'label': 'Anthropic Claude v2',
                'char_limits': 15000
            },
            {
                'func': call_bedrock_j2_ultra_model,
                'model_id': 'j2-ultra',
                'label': 'AI21 Jurassic2',
                'char_limits':8000
            },
            {
                'func': call_bedrock_j2_mid_model,
                'model_id': 'j2-mid',
                'label': 'AI21 Jurassic2 Grande',
                'char_limits':8000
            },
            {
                'func': call_bedrock_sdxl_model,
                'model_id': 'sdxl',
                'label': 'StableDiffusion SDXL'
            },
            {
                'func': call_bedrock_llama_2_13b,
                'model_id': 'llama2-13b-chat',
                'label': 'Meta Llama2-13b-chat',
                'char_limits':5000
            },
            {
                'func': call_bedrock_llama_2_70b,
                'model_id': 'llama2-70b-chat',
                'label': 'Meta Llama2-70b-chat',
                'char_limits':5000
            },
            {
                'func': call_bedrock_mistral_7b,
                'model_id': 'mistral-7b-instruct',
                'label': 'Mistral 7B Instruct',
                'char_limits':400
            },
            {
                'func': call_bedrock_mistral_8x7b,
                'model_id': 'mistral-8x7b-instruct',
                'label': 'Mistral 8x7B Instruct',
                'char_limits':400
            },
            {
                'func': call_bedrock_cohere_text_v14,
                'model_id': 'cohere text v14',
                'label': 'Cohere Command Text v14',
                'char_limits':8000
            }

        ] 
    
    #print('Incoming request for : ', model_id)
    for call_model in call_models:
        if call_model['model_id'] in model_id:
            #print('Found match request for : ', model_id, call_model)
            return call_model
    
    logger.warning('Didnt find match for requested model: {}, returning default - Claude v2!'.format(model_id))
    
    # Default return Bedrock Claude
    return {
                'func': call_bedrock_claude_model_v2,
                'model_id': 'claude-v2',
                'label': 'Anthropic Claude v2',
                'char_limits': 15000
            }

def call_bedrock_titan_text_lite_model(prompt_text, max_tokens = 4096, temperature = 0.5, top_p = 0.9, top_k = 250, stop_sequences = []):
    #model_id = 'amazon.titan-tg1-large'
    model_type = 'amazon.titan'
    model_id = 'amazon.titan-text-lite-v1'

    # Strip off newlines as it breaks the model
    prompt_text = prompt_text.replace('\n', ' ')[:BEDROCK_TITAN_PAYLOAD_LIMIT]
    
    logger.info('Invoking Bedrock Titan... with model: {}'.format(model_id))
    
    # Check if content over Bedrock Titan limit
    #if (len(prompt_text)) > BEDROCK_TITAN_PAYLOAD_LIMIT:
    #    return 'Error!! Incoming payload length over ' + str(BEDROCK_TITAN_PAYLOAD_LIMIT) \
    #        + ', please use smaller sample input!!'
        
    body_string = "{\"inputText\":\"" + f"{prompt_text}" +\
                    "\",\"textGenerationConfig\":{" +\
                    "\"maxTokenCount\":" + f"{max_tokens}" +\
                    ",\"topP\":" + f"{top_p}" +\
                    ",\"stopSequences\":" + f"{stop_sequences}" +\
                    ",\"temperature\":" + f"{temperature}" +\
                    "}}"
    logger.info('Invoking Bedrock Titan Text Lite... with model: {} and body: {}'.format(model_id, body_string))
    body = bytes(body_string, 'utf-8')
    response = None
    try:
        response = bedrockruntime.invoke_model(
            modelId = model_id,
            contentType = "application/json",
            accept = "application/json",
            body = body)
            
        
        responseBody = response['body'].read()
        json_str = responseBody.decode('utf-8')
        
        json_obj = json.loads(json_str)
        result_text = json_obj['results'][0]['outputText']
        #logger.debug('Titan payload: ', body_string, ' \n------- and associated response: ', result_text)
        logger.debug('Invoking Titan TextLite ... model: {}, response: {}'.format(model_id, responseBody))
        
        # Generate the cost and save in session
        save_cost_entry_for_model(model_id, prompt_text, responseBody)
        
        # Strip off additional quotes as it breaks the model with subsequent calls
        return result_text.strip('\"')
            
    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err
        if 'AccessDeniedException' in str(e1):
            err = 'Error!! Problem in accessing model, possible its not available!!'
            logger.error(err)
            return err
        return e1

def call_bedrock_titan_text_express_model(prompt_text, max_tokens = 4096, temperature = 0.5, top_p = 0.9, top_k = 250, stop_sequences = []):
    #model_id = 'amazon.titan-tg1-large'
    model_type = 'amazon.titan'
    model_id = 'amazon.titan-text-express-v1'

    # Strip off newlines as it breaks the model
    prompt_text = prompt_text.replace('\n', ' ')[:BEDROCK_TITAN_PAYLOAD_LIMIT]
    
    
    # Check if content over Bedrock Titan limit
    #if (len(prompt_text)) > BEDROCK_TITAN_PAYLOAD_LIMIT:
    #    return 'Error!! Incoming payload length over ' + str(BEDROCK_TITAN_PAYLOAD_LIMIT) \
    #        + ', please use smaller sample input!!'
        
    body_string = "{\"inputText\":\"" + f"{prompt_text}" +\
                    "\",\"textGenerationConfig\":{" +\
                    "\"maxTokenCount\":" + f"{max_tokens}" +\
                    ",\"topP\":" + f"{top_p}" +\
                    ",\"stopSequences\":" + f"{stop_sequences}" +\
                    ",\"temperature\":" + f"{temperature}" +\
                    "}}"
    logger.info('Invoking Bedrock Titan Text Exp... with model: {} and body: {}'.format(model_id, body_string))
    
    body = bytes(body_string, 'utf-8')
    response = None
    try:
        response = bedrockruntime.invoke_model(
            modelId = model_id,
            contentType = "application/json",
            accept = "application/json",
            body = body)
            
        
        responseBody = response['body'].read()
        json_str = responseBody.decode('utf-8')
        logger.debug('Invoking Titan TextExpress ... model: {}, response: {}'.format(model_id, responseBody))
        
        json_obj = json.loads(json_str)
        result_text = json_obj['results'][0]['outputText']
        #logger.debug('Titan payload: ', body_string, ' \n------- and associated response: ', result_text)
    
        
        # Generate the cost and save in session
        save_cost_entry_for_model(model_id, prompt_text, responseBody)
        
        # Strip off additional quotes as it breaks the model with subsequent calls
        return result_text.strip('\"')
            
    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err
        if 'AccessDeniedException' in str(e1):
            err = 'Error!! Problem in accessing model, possible its not available!!'
            logger.error(err)
            return err
        return e1
        
                
def call_bedrock_titan_embedding_text_model(prompt_text, max_tokens = 2048, temperature = 0.5, top_p = 0.9, top_k = 250, stop_sequences = []):
    #model_id = 'amazon.titan-tg1-large'
    #model_id = 'amazon.titan-text-lite-v1'
    model_id = 'amazon.titan-embed-text-v1'
    model_type = 'amazon.titan'
    
    # Strip off newlines as it breaks the model
    prompt_text = prompt_text.replace('\n', ' ')[:BEDROCK_TITAN_PAYLOAD_LIMIT]
    
    # Check if content over Bedrock Titan limit
    #if (len(prompt_text)) > BEDROCK_TITAN_PAYLOAD_LIMIT:
    #    return 'Error!! Incoming payload length over ' + str(BEDROCK_TITAN_PAYLOAD_LIMIT) \
    #        + ', please use smaller sample input!!'
        
    body_string = "{\"inputText\":\"" + f"{prompt_text}" +\
                    "\"}"
    logger.info('Invoking Bedrock Titan... with model: {} and body: {}'.format(model_id, body_string))
    body = bytes(body_string, 'utf-8')
    response = None
    try:
        response = bedrockruntime.invoke_model(
            modelId = model_id,
            contentType = "application/json",
            accept = "application/json",
            body = body)
            
        
        responseBody = response['body'].read()
        json_str = responseBody.decode('utf-8')
        logger.debug('Invoking Titan Embedding  ... model: {}, response: {}'.format(model_id, responseBody))
        json_obj = json.loads(json_str)
        logger.info('Response body as json: {}'.format(json_str))
        embeddings = json_obj['embedding']
        
        return embeddings
            
    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err
        return e1

def call_bedrock_claude_model_v3(prompt_text, max_tokens = 8192, temperature = 0.5, top_p = 1, top_k = 250):
    model_id = 'anthropic.claude-3-sonnet-20240229-v1:0'
    return call_bedrock_claude_3(prompt_text, model_id, max_tokens, temperature, top_p, top_k)

def call_bedrock_claude_model_instant_v1(prompt_text, max_tokens = 2048, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    model_id = 'anthropic.claude-instant-v1'
    return call_bedrock_claude_model(prompt_text, model_id, max_tokens, temperature, top_p, top_k, stop_sequences)

def call_bedrock_claude_model_v2_1(prompt_text, max_tokens = 2048, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    model_id = 'anthropic.claude-v2:1'
    return call_bedrock_claude_model(prompt_text, model_id, max_tokens, temperature, top_p, top_k, stop_sequences)

def call_bedrock_claude_model_v2(prompt_text, max_tokens = 2048, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    model_id = 'anthropic.claude-v2'
    return call_bedrock_claude_model(prompt_text, model_id, max_tokens, temperature, top_p, top_k, stop_sequences)

def call_bedrock_claude_model_v1(prompt_text, max_tokens = 2048, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    model_id = 'anthropic.claude-v1'
    return call_bedrock_claude_model(prompt_text, model_id, max_tokens, temperature, top_p, top_k, stop_sequences)

def call_bedrock_claude_v1_100k(prompt_text, max_tokens = 2048, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    model_id = 'anthropic.claude-v1-100k'
    return call_bedrock_claude_model(prompt_text, model_id, max_tokens, temperature, top_p, top_k, stop_sequences)

def call_bedrock_claude_v2_100k(prompt_text, max_tokens = 2048, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    model_id = 'anthropic.claude-v2-100k'
    return call_bedrock_claude_model(prompt_text, model_id, max_tokens, temperature, top_p, top_k, stop_sequences)
    
def call_bedrock_claude_model(prompt_text, model_id, max_tokens = 2048, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    body = {
        "prompt": anthropic.HUMAN_PROMPT+prompt_text+anthropic.AI_PROMPT,
        "max_tokens_to_sample": max_tokens
    }
    
    body_string = json.dumps(body)
    body_bytes = bytes(body_string, 'utf-8')
    
    
    logger.info('Invoking Bedrock Claude... model: {} with body: {}'.format(model_id, body_string))
    response = None
    try:
        response = bedrockruntime.invoke_model(
            modelId = model_id,
            contentType = "application/json",
            accept = "application/json",
            body = body_bytes)
        
        responseBody = response['body'].read()
        logger.debug('Invoking Claude  ... model: {}, response: {}'.format(model_id, response))
        json_obj = json.loads(responseBody)
        result_text = json_obj['completion']

        
        # Generate the cost and save in session
        save_cost_entry_for_model(model_id, body['prompt'], responseBody)

        return result_text
    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err

        return e1

def call_bedrock_claude_model_3(prompt_text, model_id, max_tokens = 8192, temperature = 0.5, top_p = 1, top_k = 250):
    """ invokes the new claude 3 model via the messages api """
    
    payload=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 8096,
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": prompt_text}],
                        }
                    ],
                }
            )
    try:
        
        logger.info('Invoking Bedrock Claude v3... model: {} with body: {}'.format(model_id, payload))
        
        response = bedrockruntime.invoke_model(
            modelId=model_id,
            body=payload
        )

            
        result = json.loads(response.get("body").read())
        input_tokens = result["usage"]["input_tokens"]
        output_tokens = result["usage"]["output_tokens"]
        output_list = result.get("content", [])

        logger.debug('Invoking Claude v3  ... model: {}, response: {}'.format(model_id, result))
        logger.debug("Invocation details:")
        logger.debug(f"- The input length is {input_tokens} tokens.")
        logger.debug(f"- The output length is {output_tokens} tokens.")

        logger.debug(f"- The model returned {len(output_list)} response(s):{output_list[0]['text']}" )
        
        # Generate the cost and save in session
        user_generated_prompt = True if ( AUTO_GENERATED_PROMPT not in prompt_text) else False
        save_cost_entry_for_model_tokens(model_id, input_tokens, output_tokens, user_generated_prompt)

        return output_list[0]["text"]
    except Exception as e1:
        logger.error('Error!! Failure in backend model processing!!' + str(e1))
        return str(e1)
        


def call_bedrock_cohere_text_v14(prompt_text, max_tokens = 1024, temperature = 0.5, top_p = 1, top_k = 250, stop_sequences = []):
    model_id='cohere.command-text-v14'
    body = json.dumps({
        "prompt": prompt_text,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "p": top_p
    })
    
    logger.info('Invoking Bedrock Cohere text... model: {} with body: {}'.format(model_id, body))
    response = None
    try:
        response = bedrockruntime.invoke_model(
            modelId = model_id,
            contentType = "application/json",
            accept = "application/json",
            body = body)
        
        response_body = json.loads(response.get('body').read())
        logger.debug('Invoking Cohere text  ... model: {}, response: {}'.format(model_id, response_body))
        
        result_text = response_body.get('generations')[0].get('text')
        #print(result_text)
        
        # Generate the cost and save in session
        save_cost_entry_for_model(model_id, prompt_text, responseBody)
        
        return result_text
    except Exception as e1:
        logger.error('Error!! Failure in backend model processing!!' + str(e1))
        return str(e1)

def call_bedrock_j2_ultra_model(prompt_text,max_tokens = 500, temperature = 1, top_p = 1, top_k = 250, stop_sequences = [],  countPenalty = 0, presencePenalty = 0, frequencyPenalty = 0):
    model_id = 'ai21.j2-ultra'
    model_type = 'AI21 Labs Jurassic2 Ultra'
    return call_ai21_model(model_id, model_type, prompt_text,max_tokens, temperature, top_p, top_k, stop_sequences, countPenalty, presencePenalty, frequencyPenalty)

def call_bedrock_j2_mid_model(prompt_text,max_tokens = 500, temperature = 1, top_p = 1, top_k = 250, stop_sequences = [],  countPenalty = 0,presencePenalty = 0, frequencyPenalty = 0):
    model_id = 'ai21.j2-mid'
    model_type = 'AI21 Labs Jurassic2 Mid'  
    return call_ai21_model(model_id, model_type, prompt_text,max_tokens, temperature, top_p, top_k, stop_sequences, countPenalty, presencePenalty, frequencyPenalty)


def call_ai21_model(model_id, model_type, prompt_text,max_tokens, temperature, top_p, top_k, stop_sequences, countPenalty, presencePenalty, frequencyPenalty):
    
    # Strip off newlines and tabs as it breaks the model
    prompt_text = prompt_text.replace('\n', ' ').replace('\t', ' ')
    
    body_string = "{\"prompt\":\"" + f"{prompt_text}" + "\"" +\
                    ",\"maxTokens\":" + f"{max_tokens}" +\
                    ",\"temperature\":"  + f"{temperature}" +\
                    ",\"topP\":" + f"{top_p}" +\
                    ",\"stopSequences\": " + f"{stop_sequences}" +\
                    ",\"countPenalty\":{\"scale\": " + f"{countPenalty}" + "}" +\
                    ",\"presencePenalty\":{\"scale\": " + f"{presencePenalty}" + "}" +\
                    ",\"frequencyPenalty\":{\"scale\": " + f"{frequencyPenalty}" + "}" +\
                    "}"
    body = bytes(body_string, 'utf-8')
    logger.debug('Invoking Bedrock AI21 Jurassic  ... model: {}, body: {}'.format(model_id, body_string))
    try:
        response = bedrockruntime.invoke_model(
            modelId = model_id,
            contentType = "application/json",
            accept = "application/json",
            body = body)
        response_lines = response['body'].readlines()
        logger.debug('Invoking AI21  ... model: {}, response: {}'.format(model_id, response))
        json_str = response_lines[0].decode('utf-8')
        json_obj = json.loads(json_str)
        result_text = json_obj['completions'][0]['data']['text']
        
        # Generate the cost and save in session
        save_cost_entry_for_model(model_id, prompt_text, response)
        
        return result_text
    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err

        return e1
# "body": "{"text_prompts": [{"text":"this is where you place your input text"}],"cfg_scale":10,"seed":0,"steps":50}"
                                         
def call_bedrock_sdxl_model(prompt_text, style_preset='digital-art',height=512,width=512,image_strength=0.5,cfg_scale=10,seed=1885337276,steps=100):
    model_id = 'stability.stable-diffusion-xl-v1'
    model_type = 'sd.sdxl'
    
    payload = { "text_prompts": [ 
                        { "text": prompt_text} 
                    ] ,
                    "cfg_scale": cfg_scale,
                    "height": height,
                    "width": width,
                    "image_strength": image_strength,
                    "style_preset": style_preset,
                    "seed": seed,
                    "steps": steps
                }
                
    body = json.dumps(payload).encode('utf-8')
    logger.info('Invoking Bedrock stable-diffusion... model: {} and request:{}'.format(model_id, payload))
    
    try:
        response = bedrockruntime.invoke_model(
            modelId = model_id,
            contentType = "application/json",
            accept = "application/json",
            body = body)
        response = json.loads(response['body'].read())
        logger.debug('Invoking Stable diffusion  ... model: {}, response: {}'.format(model_id, response))
        return response

    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err
    
        return e1

def call_bedrock_llama_2_13b(query, max_new_tokens=4096, temperature = 0.6, top_p = 0.9):
    
    return call_bedrock_llama_2_code_response(query, 'meta.llama2-13b-chat-v1', max_new_tokens, temperature, top_p)
    

def call_bedrock_llama_2_70b(query, max_new_tokens=4096, temperature = 0.6, top_p = 0.9):
    
    return call_bedrock_llama_2_code_response(query, 'meta.llama2-70b-chat-v1', max_new_tokens, temperature, top_p)


def call_bedrock_llama_2_code_response(query, model_id, max_new_tokens, temperature, top_p):
    
    payload = {"prompt": query, "max_gen_len": 2000, "top_p": top_p, "temperature": temperature }
    body = json.dumps(payload).encode('utf-8')
    #logger.debug('Llama Incoming payload: {}', payload)
    logger.info('Invoking Bedrock Llama2... model: {} and request:{}'.format(model_id, payload))
    
    try:
        
        response = bedrockruntime.invoke_model( modelId = model_id, 
                                                contentType="application/json", 
                                                accept = "application/json",
                                                body=body
                                            )
        response = json.loads(response['body'].read())
        logger.debug('Invoking Llama  ... model: {}, response: {}'.format(model_id, response))
        result_text = response['generation']

        # Generate the cost and save in session
        save_cost_entry_for_model(model_id, query, response)
        
        # Strip off additional quotes as it breaks the model with subsequent calls
        return result_text #.strip('\"')

    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err
        return e1

def call_bedrock_mistral_7b(query, max_tokens = 500, temperature = 0.7, top_p = 0.7, top_k = 50, stop_sequences = []):
    
    model_id = "mistral.mistral-7b-instruct-v0:2"
    return call_bedrock_mistral(query, model_id,max_tokens, temperature, top_p, top_k, stop_sequences)

def call_bedrock_mistral_8x7b(query, max_tokens = 500, temperature = 0.7, top_p = 0.7, top_k = 50, stop_sequences = []):
    
    model_id = "mistral.mistral-8x7b-instruct-v0:1"
    return call_bedrock_mistral(query, model_id,max_tokens, temperature, top_p, top_k, stop_sequences)
        

def call_bedrock_mistral(query, model_id,max_tokens, temperature, top_p, top_k, stop_sequences):
    

    payload = {"prompt": f'<s>[INST]{query}.[/INST]\\', "max_tokens": max_tokens, "top_k": top_k,  "top_p": top_p, "temperature": temperature }
    body = json.dumps(payload).encode('utf-8')
    logger.info('Invoking Bedrock Mistral... model: {} and request:{}'.format(model_id, payload))
    
    
    try:
        
        response = bedrockruntime.invoke_model( modelId = model_id,
                                                contentType="application/json", 
                                                accept = "application/json",
                                                body=body
                                            )
        response = json.loads(response['body'].read())
        logger.debug('Invoking Mistral  ... model: {}, response: {}'.format(model_id, response))
        result_text = response['outputs'][0]['text']

        # Generate the cost and save in session
        save_cost_entry_for_model(model_id, query, response)
        
        # Strip off additional quotes as it breaks the model with subsequent calls
        return result_text #.strip('\"')

    except Exception as e1:
        logger.exception(e1)
        if 'Throttling' in str(e1):
            err = 'Error!! Request Throttled!! Please retry later'
            logger.error(err)
            return err
        if 'ValidationException' in str(e1):
            err = 'Error!! Failure in backend model processing!!'
            logger.error(err)
            return err
        return e1        
       
def to_camel_case(text):
    s = text.replace("-", " ").replace("_", " ").replace('.', ' ').replace(':', '.')
    s = s.split()
    if len(text) == 0:
        return text
    return ' '.join(i.capitalize() for i in s[0:])


create_model_function_mapping()
if has_jumpstart == True:
    genai_models.append('Sagemaker Jumpstart')

for model_name in genai_model_entries.keys():
    genai_model_functions[model_name] = find_bedrock_model(genai_model_entries[model_name])
genai_model_functions["sagemaker jumpstart"] = get_jumpstart_model()


#logger.info('genai-models: {}'.format(genai_models))
#logger.info('genai-genai_model_functions: {}'.format(genai_model_functions))

default_genai_model = 'Anthropic Claude V2.1'
default_genai_model_index = -1

try:
    
    default_genai_model_index = genai_models.index(default_genai_model)
except:
    logger.info('Didnt find default model ...Claude V2.1')
    
    if default_genai_model_index == -1:
        just_claude_index = -1
        other_match = None
        for key in genai_models:
            if 'Claude' in key and '2' in key:
                default_genai_model = key
                default_genai_model_index = genai_models.index(key)
                break
            elif 'Claude' in key:
                other_match = key
                just_claude_index =  genai_models.index(key)
        
        if default_genai_model_index == -1 and just_claude_index != -1:
            default_genai_model = other_match
            default_genai_model_index = just_claude_index
            
logger.info('######## Default Genai model: {}, index: {}, call_model: {}'.format(default_genai_model, default_genai_model_index, genai_model_functions[default_genai_model] ) )


    

