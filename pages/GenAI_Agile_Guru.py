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

import boto3
import streamlit as st
import os
from utils import gen_ai_selector
from utils import cognito_helper

import pages.imports.sts_assume_role as boto3_session


autorefresh_session = boto3_session.run_autorefresh_session()
s3 = autorefresh_session.client('s3')
comprehend = autorefresh_session.client('comprehend')


if 'user_stories' not in st.session_state:
    st.session_state['user_stories'] = None
if 'data_model' not in st.session_state:
    st.session_state['data_model'] = None
if 'api_specs' not in st.session_state:
    st.session_state['api_specs'] = None


# Get environment variables
bucket = os.environ['bucket']
languages = ['English', 'Spanish', 'German', 'Portugese', 'Irish', 'Star Trek - Klingon', 'Star Trek - Ferengi', 'Italian', 'French', 'Japanese', 'Mandarin', 'Tamil', 'Hindi', 'Telugu', 'Kannada', 'Arabic', 'Hebrew']

st.set_page_config(page_title="GenAI Agile Guru", page_icon="high_brightness")


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


st.markdown("# From epic to Epic in seconds")
st.sidebar.header("GenAI Agile Guru")

genai_models = gen_ai_selector.genai_models
default_model = gen_ai_selector.default_genai_model_index
model = st.sidebar.selectbox('Select a FM', genai_models, index=default_model)

models = gen_ai_selector.genai_model_functions



def GetAnswers(query):
    us_answer = None
    func = models[model]['func']
    generated_text = func('Create 5 agile scrum user stories and acceptance criteria for each user story in '+language+' for '+ query.strip("query:"))
    if generated_text != '' and generated_text != None and 'Error' not in generated_text:
        generated_text = generated_text.replace("$","\$")
        us_answer = str(generated_text)
    else:
        us_answer = 'Sorry!! did not find an answer to your question, please try again'   
    return us_answer                       

st.write("**Instructions:** \n - Type an epic story \n - You will see user stories, data model, api specs, and BDD scenarios automatically generated for your epic \n")

p_summary = '''
- funds transfer for banking \n
- login to member portal and check balance \n
- track and redeem rewards points \n
- create customized landing page for website \n
'''
  
st.sidebar.write('### Suggested epics to get started \n\n' + 
            p_summary)

input_text = st.text_input('**Type an epic**', key='text_ag')
default_lang_ix = languages.index('English')
language = st.selectbox(
    '**Select an output language.**',
    options=languages, index=default_lang_ix)
generated_text = ''
dm_generated_text = ''
as_generated_text = ''
bd_generated_text = ''
us_answer = ''
as_answer = ''
dm_answer = ''
bd_answer = ''
func = models[model]['func']

if input_text != '':
    us_answer = GetAnswers(input_text)
    tab1, tab2, tab3, tab4 = st.tabs(["User Stories", "Data Model", "API Specs", "BDD Secenarios"])
    #c1, c2 = st.columns(2)
    with tab1:
        if us_answer:
            st.write("**User stories for your epic**")
            st.write(us_answer)
    with tab2:
        dm_generated_text = func('Create a data model in '+language+' for each of the user stories in '+str(us_answer))
        if dm_generated_text != '' and dm_generated_text != None and 'Error' not in dm_generated_text:
            #print('DM!!', dm_generated_text)
            dm_generated_text = dm_generated_text.replace("$","\$")
            dm_answer = str(dm_generated_text)
            st.session_state.data_model = dm_answer
        else:
            dm_answer = 'Sorry!! did not find an answer to your question, please try again' 
        if dm_answer:
            st.write("**Data model for your user stories**")    
            st.write(dm_answer)
    with tab3:
        as_generated_text = func('Create microservices API specifications in '+language+' for each of the data models in '+ str(dm_answer))
        if as_generated_text != '' and as_generated_text != None and 'Error' not in as_generated_text:
            #print('AS!!', as_generated_text)
            as_generated_text = as_generated_text.replace("$","\$")
            as_answer = str(as_generated_text)
            st.session_state.api_specs = as_answer
        else:
            as_answer = 'Sorry!! did not find an answer to your question, please try again'
        if as_answer:        
            st.write("**API Specs for your user stories**")  
            st.write(as_answer)
    with tab4:
        bd_generated_text = func('Create behavior driven development scenarios using cucumber in '+language+' for each of the user stories in '+ str(us_answer))
        if bd_generated_text != '' and bd_generated_text != None and 'Error' not in bd_generated_text:
            #print('BD!!', bd_generated_text)
            bd_generated_text = bd_generated_text.replace("$","\$")
            bd_answer = str(bd_generated_text)
        else:
            bd_answer = 'Sorry!! did not find an answer to your question, please try again'
        if bd_answer:
            st.write("**BDD Scenarios for your user stories**")
            st.write(bd_answer)
    
st.sidebar.markdown('### :red[Cost of Invocations] \n' 
                + gen_ai_selector.report_cost()) 
