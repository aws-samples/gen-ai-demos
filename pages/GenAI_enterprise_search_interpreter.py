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
import streamlit as st
import datetime
from io import BytesIO
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
import base64
import uuid
import ai21
import string
import anthropic
import os

from utils import gen_ai_selector
from utils import cognito_helper

import pages.imports.sts_assume_role as boto3_session


autorefresh_session = boto3_session.run_autorefresh_session()
comprehend = autorefresh_session.client('comprehend')
bedrock = autorefresh_session.client('bedrock')
kendra = autorefresh_session.client('kendra')

# Get environment variables
fsi_index_id = os.getenv('fsi_index_id', '')
energy_index_id = os.getenv('energy_index_id', '')
travel_index_id = os.getenv('travel_index_id', '')
legal_index_id = os.getenv('legal_index_id', '')
bucket = os.environ['bucket']

st.set_page_config(page_title="GenAI Enterprise Search and Interpreter", page_icon="mag_right")

if 'stage' not in st.session_state:
    st.session_state.stage = 1
if 'login_form_rendered' not in st.session_state:
    st.session_state.login_form_rendered = False
if 'login_form_rendered_page' not in st.session_state:
    st.session_state.login_form_rendered_page = ''
    
cognito_helper.manage_session()

if not st.session_state["authenticated"]:
    cognito_helper.login()    
    st.stop()



st.markdown(
    """
    ### :red[Note] 
    - These demos are for informational purposes only.
    - Use these selection of [samples for playing with the demos](https://github.com/aws-samples/gen-ai-samples/sample-artifacts). 
    - The demos should not be considered as an actual prototype or working version of a proposed solution
    """)


    
st.markdown("# GenAI Enterprise Search")
st.sidebar.header("GenAI search and interpret enterprise content")
st.sidebar.markdown("### Make your pick")
industry = ''
industry = st.sidebar.selectbox(
    'Select an industry',
    ('Financial Services', 'Energy', 'Legal', 'Travel and Transport'))

if industry == 'Financial Services':
    st.sidebar.markdown('''
        ### Example prompts you can try \n\n
        What is a company's EPS and what does it mean? \n
        Why are EU members not aligned on fiscal policy? \n
    ''')
elif industry == 'Energy':
    st.sidebar.markdown('''
        ### Example prompts you can try \n\n
        List the steps how oil is refined? \n
        What are the risks in hydrocarbon transport? \n
    ''')
elif industry == 'Travel and Transport':
    st.sidebar.markdown('''
        ### Example prompts you can try \n\n
        What is the maximum range for Airbus A330? \n
        What is the final approach speed for A350? \n
    ''')
elif industry == 'Legal':
    st.sidebar.markdown('''
        ### Example prompts you can try \n\n
        Who are the buyers and sellers mentioned in the contract? \n
        What is the closing date for the contract? \n
        What documents do the buyers need to approve? \n
    ''')
model = 'Anthropic Claude'
#model = st.sidebar.selectbox(
#    'Select a LLM',
#    ('J2 Jumbo Instruct', 'Anthropic Claude'))



genai_models = gen_ai_selector.genai_models
default_model = gen_ai_selector.default_genai_model_index
print('DEFAULT MODEL>...', default_model)
model = st.sidebar.selectbox('Select a FM', genai_models, index=default_model)

models = gen_ai_selector.genai_model_functions
    
def call_Kendra(query_string, index_id):
    d = 0
    a = 0
    answer_text = ''
    document_text = ''
    result_set = []
    result_dict = {}
    sources_list = []
    result = ' '    
    
    if index_id is None or index_id == '':
        result_dict['snippet'] = ' '
        result_dict['sources'] = ' '    
        return result_dict
    
    response = kendra.query(
            QueryText = query_string,
            IndexId = index_id)
    
    for query_result in response["ResultItems"]:
        entry = {}
        if query_result["Type"]=="ANSWER" or query_result["Type"]=="QUESTION_ANSWER":
            a += 1
            if a <= 1:
                answer_text = query_result["DocumentExcerpt"]["Text"]
                src = "Document: [Link]({})".format(query_result['DocumentAttributes'][0]['Value']['StringValue'])
                if len(query_result['DocumentAttributes']) > 1:
                    src += " and Page: {}".format(query_result['DocumentAttributes'][1]['Value']['LongValue'])
                
                entry['answer'] = answer_text
                entry['src'] = src
                

        elif query_result["Type"]=="DOCUMENT":
            d += 1
            if "DocumentTitle" in query_result:
                document_title = query_result["DocumentTitle"]["Text"]
                #print("Title: " + document_title)
            
            document_text = query_result["DocumentExcerpt"]["Text"]
            src = "Document: [Link]({})".format(query_result['DocumentAttributes'][0]['Value']['StringValue'])
            
            if len(query_result['DocumentAttributes']) > 1:
                src += " and Page: {}".format(query_result['DocumentAttributes'][1]['Value']['LongValue'])
            
            # if src not in sources_list:
            #     sources_list.append(src)
            # print('document text: ', document_text)
            entry['answer'] = document_text
            entry['src'] = src

        if len(entry) > 0:
            result_set.append(entry)
        
    # print('Final document_text: ', document_text)
    # result = answer_text +' '+document_text
    # print('Final result text: ', result)
    
    # result_dict['snippet'] = result
    # result_dict['sources'] = sources_list

    return result_set


def GetAnswers(query):
    answer = None
    sources = ''
    if industry.lower() == 'financial services':
        index_id = fsi_index_id
    elif industry.lower() == 'energy':
        index_id = energy_index_id
    elif industry.lower() == 'travel and transport':
        index_id = travel_index_id
    elif industry.lower() == 'legal':
        index_id = legal_index_id
    else:
        index_id = ''
    
    func = models[model]['func']
    
    generated_text = ''
    # Kendra calls
    results = call_Kendra(query.strip("query:"), index_id)
    # Based on model selected
    
    if len(results) == 0: 
        generated_text = func(query.strip("query:"))

        if generated_text is None or generated_text == '':
            answer = 'Sorry, did not find an answer to your question, please try again or with different input' 
        elif 'Error' not in generated_text :
            answer = str(generated_text) 
            answer = answer.replace("$","\$")
        else:
            answer = generated_text + ' Please try again or with different input' 

    else:
        full_snippet = ''

        for idx, entry in enumerate(results):
            if idx <= 3:
                full_snippet += entry['answer'] + '\n'
                sources += entry['src'] + '\n\n\n'
        
        formatted_snippet = full_snippet.translate(str.maketrans('','',string.punctuation))
        formatted_snippet = formatted_snippet.replace('\n',' ')
        
        #st.write("Search results for: {}\n".format(query.strip()))
        #for entry in results:
        #    st.write('- ', entry['answer'].replace("\n",".. "))
        #    st.write('    Source ', entry['src'])
        
        
        generated_text = func(formatted_snippet+'. Answer from this text:'+query.strip("query:"))
        
        #print('generated result text: ', generated_text)

        if generated_text is None or generated_text == '':
            answer = 'Sorry, did not find an answer to your question, please try again' 
        elif 'Error' not in generated_text :
            answer = str(generated_text) 
            answer = answer.replace("$","\$")
            answer = answer + 'Document sources are: \n\n' + sources 
        else:
            answer = generated_text + ' Please try again or with different input' 

        
    return answer 

st.write("**Instructions:** \n - Type your query \n - You will get the top answer explained. If a match was not found in Amazon Kendra, you will get a general answer for your query \n")
input_text = st.text_input('**What are you searching for?**', key='text')
result = ''
if input_text != '':
    result = GetAnswers(input_text)
    result = result.replace("$","\$")
    st.write('\nAnswers from Model')
    st.write(result)
    
    if 'Jumpstart' in model:
        st.write("Source: "+ model + ': ' + pref_jumpstart_model )
    else:
        st.write('Source: ' + model)

func = models[model]['func']

if result != '':
    #if model == 'anthropic claude':  
    p_text = func('Generate three prompts to query the text: '+ result)
    p_text1 = []
    p_text2 = ''
    if p_text != '':
        p_text = p_text.replace("$","\$")
        p_text1 = p_text.split('\n')
        for i,t in enumerate(p_text1):
            if i > 1:
                p_text2 += t.split('?')[0]+'\n\n'
            else:
                p_text2 += t + '\n\n'                
        p_summary = p_text2
        
        st.sidebar.markdown('### Suggested prompts for further insights \n\n' + 
            p_summary)
    
st.sidebar.markdown('### :red[Cost of Invocations] \n' 
                + gen_ai_selector.report_cost())
