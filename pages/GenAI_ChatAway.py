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
import uuid
from streamlit_chat import message
from boto3.dynamodb.conditions import Key
import os
from utils import gen_ai_selector
from utils import cognito_helper

import pages.imports.sts_assume_role as boto3_session


autorefresh_session = boto3_session.run_autorefresh_session()
comprehend = autorefresh_session.client('comprehend')
bedrock = autorefresh_session.client('bedrock')

# Get environment variables
stack_id = os.environ.get('STACK_ID')

# create a unique widget
if 'key' not in st.session_state:
    st.session_state.key = str(uuid.uuid4())


if 'sessionID' not in st.session_state:
    st.session_state['sessionID'] = str(uuid.uuid4())
if 'prevText' not in st.session_state:
    st.session_state['prevText'] = None
if 'count' not in st.session_state:
    st.session_state['count'] = 0
if 'ca_chat_messages' not in st.session_state:
    st.session_state.ca_chat_messages = [{}]

def get_old_chats():
    return st.session_state.ca_chat_messages

def store_chat(session, turn, question, answer):
    message_dict = {}
    message_dict['session'] = session
    message_dict['turn'] = turn
    message_dict['question'] = question
    message_dict['answer'] = answer
    st.session_state.ca_chat_messages.append(message_dict)

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
    - The demos should not be considered as an actual prototype or working version of a proposed solution
    """)

st.sidebar.header("GenAI ChatAway")


genai_models = gen_ai_selector.genai_models
default_model = gen_ai_selector.default_genai_model_index
model = st.sidebar.selectbox('Select a FM', genai_models, index=default_model)

models = gen_ai_selector.genai_model_functions

if 'Jumpstart' in model:
    st.markdown("# Chat with "+ model + ': ' + pref_jumpstart_model )
else:
    st.markdown("# Chat with "+ model)
    
#model = 'Anthropic Claude'

func = models[model]['func']



def GetAnswers(query):
    pii_list = []
    sentiment = comprehend.detect_sentiment(Text=query, LanguageCode='en')['Sentiment']
    lang = comprehend.detect_dominant_language(Text=query)
    lang_code = str(lang['Languages'][0]['LanguageCode']).split('-')[0]
    if lang_code in ['en']:
        resp_pii = comprehend.detect_pii_entities(Text=query, LanguageCode=lang_code)
        for pii in resp_pii['Entities']:
            if pii['Type'] not in ['NAME','URL','AGE','ADDRESS','DATE_TIME']:
                pii_list.append(pii['Type'])
        if len(pii_list) > 0:
            answer = "I am sorry but I found PII entities " + str(pii_list) + " in your query. Please remove PII entities and try again."
            return answer
    #query_type = ''
    #if "you" in query:
    #    query_type = "BEING"

    if query == "cancel":
        answer = 'It was swell chatting with you. Goodbye for now'

    #elif query_type == "BEING":
    #    answer = 'Kindly rephrase your question keeping it impersonal and try again.'
            
    else:
        func = models[model]['func']
        answer = str(func(query))   
    return answer          



st.write("**Instructions:** \n - Type your query in the search bar \n - Only last five chats displayed for brevity \n")
input_text = st.text_input('**Chat with me**', key='chat_text')
p_summary = ''
func = models[model]['func']
if input_text != '':
    message(input_text, is_user=True, key=str(uuid.uuid4()))

    if st.session_state.prevText is not None and len(st.session_state.prevText) > 1:
        result = GetAnswers('Answer from this text if the question is related to this text. Otherwise answer the question directly without referring to this text: '+str(st.session_state.prevText)+' ' + input_text)
    else:
        result = GetAnswers(input_text)
        

    if result:
        if '$' in result:
            result = result.replace("$","\$")
        st.session_state.prevText = result
    
        message(result, key=str(uuid.uuid4()))
        if int(st.session_state.count) <= 5:
            old_chats = get_old_chats()
            if old_chats:
                for chat in old_chats:
                    if 'question' in chat:
                        message(chat['question'], is_user=True, key=str(uuid.uuid4()))
                    if 'answer' in chat:
                        message(chat['answer'], key=str(uuid.uuid4()))
        else:
            st.session_state.count == 0

        st.session_state.count = int(st.session_state.count) + 1
        store_chat(st.session_state.sessionID, st.session_state.count, input_text, result)
        p_text = func('Generate three prompts to query the text: '+ result)
        p_text1 = []
        p_text2 = ''
        if p_text is not None and p_text != '' and 'Error' not in p_text:
            p_text.replace("$","USD")
            p_text1 = p_text.split('\n')
            for i,t in enumerate(p_text1):
                if i > 1:
                    p_text2 += t.split('\n')[0]+'\n\n'
                else:
                    p_text2 += t + '\n\n'
                    
            p_summary = p_text2
        st.sidebar.markdown('### Suggested prompts for further insights \n\n' + 
                p_summary)
    
st.sidebar.markdown('### :red[Cost of Invocations] \n' 
                + gen_ai_selector.report_cost())
