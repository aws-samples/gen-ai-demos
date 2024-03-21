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
import textract
from pypdf import PdfReader
import os
from utils import gen_ai_selector
from utils import cognito_helper


import pages.imports.sts_assume_role as boto3_session

key = os.environ['AWS_ACCESS_KEY_ID']
secret = os.environ['AWS_SECRET_ACCESS_KEY']
region = os.environ['AWS_DEFAULT_REGION']

autorefresh_session = boto3_session.run_autorefresh_session()
comprehend = autorefresh_session.client('comprehend')
bedrock = autorefresh_session.client('bedrock')

# Get environment variables

bucket = os.environ['bucket']
s3_bucket = os.environ['bucket']  # bucket that contains demo samples
s3_prefix = 'general/content'

if 'img_summary' not in st.session_state:
    st.session_state['img_summary'] = None
if 'csv_summary' not in st.session_state:
    st.session_state['csv_summary'] = None
if 'new_contents' not in st.session_state:
    st.session_state['new_contents'] = None
if 'label_text' not in st.session_state:
    st.session_state['label_text'] = None
    

s3 = boto3.client('s3',region_name=region,aws_access_key_id=key,aws_secret_access_key=secret)
comprehend = boto3.client('comprehend',region_name=region,aws_access_key_id=key,aws_secret_access_key=secret)
rekognition = boto3.client('rekognition',region_name=region,aws_access_key_id=key,aws_secret_access_key=secret)

content_analyzer_samples_folder = 'content-analyzer-samples/'


paginator = s3.get_paginator('list_objects_v2')
content_entries = paginator.paginate(Bucket=bucket)
sample_contents = ['Select...']

for content_entry_page in content_entries:
    for content_entry in content_entry_page['Contents']:
        entry = content_entry['Key']
        if "content-analyzer" in entry.lower():
            #if not ( entry.endswith('/') or entry.endswith('.wav') or entry.endswith('.mp3') or entry.endswith('.mp4')):
            if entry.split('/')[1] != '':
                sample_contents.append(entry.split('/')[1])


p_summary = ''
st.set_page_config(page_title="GenAI Content Analyzer", page_icon="sparkles")

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

st.markdown("# Analyze any content and derive insights")
st.sidebar.header("GenAI Content Analyzer V2")
values = [1, 2, 3]
default_ix = values.index(3)
ftypes = ['csv', 'pptx', 'rtf','xls','xlsx','txt', 'pdf', 'doc', 'docx', 'json','ipynb','py','java']
atypes = ['csv', 'pptx', 'rtf','xls','xlsx','txt', 'pdf', 'doc', 'docx', 'json','ipynb','py','java', 'png', 'jpg']
languages = ['English', 'Spanish', 'German', 'Portugese', 'Irish', 'Star Trek - Klingon', 'Star Trek - Ferengi', 'Italian', 'French', 'Japanese', 'Mandarin', 'Tamil', 'Hindi', 'Telugu', 'Kannada', 'Arabic', 'Hebrew']
p_count = st.sidebar.selectbox('Select the count of auto-prompts to consider', values, index=default_ix)
default_lang = languages.index('English')

hallucinegator = "With reference to science, physics, math, and programming languages as we know it, what is the hallucination or false or illogical claim in this generated content: "

genai_models = gen_ai_selector.genai_models
default_model = gen_ai_selector.default_genai_model_index
model = st.sidebar.selectbox('Select a FM', genai_models, index=default_model)

models = gen_ai_selector.genai_model_functions

func = models[model]['func']
chunk = models[model]['char_limits']


def readpdf(filename):
    # creating a pdf reader object
    reader = PdfReader(filename)
    # getting a specific page from the pdf file
    raw_text = []
    for page in reader.pages:
        raw_text.append(page.extract_text())
    return '\n'.join(raw_text)

def GetAnswers(original_text, query):
    generated_text = ''
    generated_text = func(original_text[:chunk] +'. Answer from this text with no hallucinations, false claims or illogical statements: '+ query.strip("query:"))
    
    if generated_text is None or generated_text == '':
        answer = 'Sorry!! did not find an answer to your question, please try again'   
    elif 'Error' in generated_text:
        answer = str(generated_text)
    else:
        answer = str(generated_text) 
        
    return answer          



def upload_image_detect_labels(chosen_content_key):
    summary = ''
    label_text = ''
    response = rekognition.detect_labels(
        Image={'S3Object': { 'Bucket': bucket, 'Name': chosen_content_key }},
        Features=['GENERAL_LABELS']
    )
    text_res = rekognition.detect_text(
        Image={'S3Object': { 'Bucket': bucket, 'Name': chosen_content_key }}
    )

    celeb_res = rekognition.recognize_celebrities(
        Image={'S3Object': { 'Bucket': bucket, 'Name': chosen_content_key }}
    )

    for celeb in celeb_res['CelebrityFaces']:
        label_text += celeb['Name'] + ' ' 

    for text in text_res['TextDetections']:
        label_text += text['DetectedText'] + ' '

    for label in response['Labels']:
        label_text += label['Name'] + ' '

    st.session_state.label_text = label_text
    
    func = models[model]['func']
    generated_text = str(func('Explain the contents of this image in 300 words from these labels in ' +language+ ': '+ label_text))

    if generated_text != '':
        if '$' in generated_text:
            summary = str(generated_text).replace("$","\$")
        else:
            summary = generated_text 
        
    return summary    

def upload_csv_get_summary(file_type, s3_file_name):
    summary = ''
    file_path_tokens = s3_file_name.split('/')
    local_file = file_path_tokens[len(file_path_tokens) - 1]
    print ('local_file: {}, s3 path: {}'.format(local_file, s3_file_name))
    s3.download_file(s3_bucket, s3_file_name, local_file)
    
    if file_type not in ['py','java','ipynb','pdf']:
        contents = textract.process(local_file).decode('utf-8')
        new_contents = contents[:chunk].replace('$','\$')
    elif file_type == 'pdf':
        contents = readpdf(local_file)
        new_contents = contents[:chunk].replace("$","\$")
    else:
        with open(local_file, 'rb') as f:
            contents = f.read()
        new_contents = contents[:chunk].decode('utf-8')
    
    func = models[model]['func']
    generated_text = func('Create a 300 words summary of this document in ' +language+ ': '+ new_contents)
    if generated_text != '':
        if '$' in generated_text:
            summary = str(generated_text).replace("$","\$")
        else:
            summary = generated_text
        
    return new_contents, summary    

st.write("**Instructions:** \n " \
         "1. Select an output language. \n" \
         "2. Select a sample content from available list or your own content. \n" \
         "3. You will see summary generated. \n" \
         "4. Type your queries in the search bar to get conversation insights")

#st.markdown('`Going with pre-available sample content!!`')
c1, c2 = st.columns(2)

c1.subheader('Select a content sample')
chosen_content = c1.selectbox(
    'Select a sample content from this list',
        sample_contents
    )

c2.subheader("Select an output language")
language = c2.selectbox(
    'Select an output language from list of available options.',
    options=languages, index=default_lang, key='selector')

img_summary = ''
csv_summary = ''
file_type = ''
new_contents = ''
if chosen_content != 'Select...':
    
    if 'jpg' in chosen_content or 'png' in chosen_content or 'jpeg' in chosen_content:
        #st.session_state.img_summary = None
        file_type = 'image'        
        c1.success(chosen_content + ' is ready for submission')
        if c1.button('Submit'):
            with st.spinner('Starting summarization with Amazon Rekognition label detection...'):
                img_summary = upload_image_detect_labels(content_analyzer_samples_folder+chosen_content)
                img_summary = img_summary.replace("$","\$")
                if len(img_summary) > 5:
                    st.session_state['img_summary'] = img_summary
                    st.session_state['csv_summary'] = None
                st.success('Image summary generated')
    elif str(chosen_content).split('.')[1] in ftypes:
        file_type = str(chosen_content).split('.')[1]   
        c1.success(chosen_content + ' is ready for upload')
        if c1.button('Submit'):
            with st.spinner('Starting summarization...'):
                new_contents, csv_summary = upload_csv_get_summary(file_type, content_analyzer_samples_folder+chosen_content)
                csv_summary = csv_summary.replace("$","\$")
                if len(csv_summary) > 5:
                    st.session_state['csv_summary'] = csv_summary
                    st.session_state['img_summary'] = None
                new_contents = new_contents.replace("$","\$")
                st.session_state.new_contents = new_contents
                st.success('Content summary generated')


h_results = ''
p1 = ''
m_summary = ''

target_content = None
if chosen_content != 'Select...':
    target_content = chosen_content

if target_content is not None:    
    func = models[model]['func']

    if st.session_state.img_summary:
        if len(st.session_state.img_summary) > 5:
            with open(target_content, 'wb') as f:
                s3.download_fileobj(bucket, content_analyzer_samples_folder+target_content, f)
            st.image(target_content)
            st.markdown('**Image summary**: \n')
            st.write(str(st.session_state['img_summary']))
            p_text = func('Generate '+str(p_count)+' prompts to query the summary: '+ st.session_state.img_summary)
            p_text1 = []
            p_text2 = ''
            if p_text != '':
                p_text.replace("$","\$")
                p_text1 = p_text.split('\n')
                for i,t in enumerate(p_text1):
                    if i > 1:
                        p_text2 += t.split('\n')[0]+'\n\n'
                    else:
                        p_text2 += t + '\n\n'                        
                p_summary = p_text2
            st.sidebar.markdown('### Generated auto-prompts \n\n' + 
                        p_summary)
            st.markdown('### Hallucination Analysis')
            if st.button("Halluci-Negator"):
                tab1, tab2 = st.tabs(["Hallucination Analysis", "Rewritten Summary"])
                with tab1:
                    h_results = func(hallucinegator+" "+st.session_state.img_summary[:chunk]+" based on the original data provided in "+st.session_state.label_text)
                    h_results = h_results.replace("$", "\$")
                    st.write(h_results)
                with tab2:
                    
                    m_summary = func("Rewrite a 300 words summary in "+language+" from "+st.session_state.img_summary+" without hallucinations, false claims or illogical statements sticking only to available factual data")
                    st.write(m_summary)
    elif st.session_state.csv_summary:
        if len(st.session_state.csv_summary) > 5:
            st.markdown('**Summary**: \n')
            st.write(str(st.session_state.csv_summary).replace("$","\$"))
            p_text = func('Generate '+str(p_count)+' prompts to query the text: '+ st.session_state.csv_summary[:chunk])
            p_text1 = []
            p_text2 = ''
            if p_text != '':
                p_text.replace("$","\$")
                p_text1 = p_text.split('\n')
                for i,t in enumerate(p_text1):
                    if i > 1:
                        p_text2 += t.split('\n')[0]+'\n\n'
                    else:
                        p_text2 = t.split('\n')[0]+'\n\n'
                p_summary = p_text2
                
            st.sidebar.markdown('### Generated auto-prompts \n\n' + 
                        p_summary)
            st.markdown('### Hallucination Analysis')
            if st.button("Halluci-Negator"):
                tab1, tab2 = st.tabs(["Hallucination Analysis", "Rewritten Summary"])
                with tab1:
                    h_results = func(hallucinegator+" "+st.session_state.csv_summary[:5000]+" based on original data provided in "+st.session_state.new_contents[:5000])
                    h_results = h_results.replace("$", "\$")
                    st.write(h_results)
                with tab2:
                    m_summary = func('Rewrite a 300 words summary in '+language+' from '+st.session_state.new_contents[:8000]+' without hallucinations, false claims or illogical statements sticking only to available factual data')
                    st.write(m_summary)

input_text = st.text_input('**What insights would you like?**', key='text')
if input_text != '':
    file_type = str(target_content).split('.')[1]
    if st.session_state.img_summary:
        result = GetAnswers(st.session_state.img_summary,input_text)
        if (result is not None):
            result = result.replace("$","\$")
            st.write(result)
    elif st.session_state.csv_summary:
        
        print('Chosen content: ', chosen_content)
        #print('uploaded content: ', str(uploaded_img))
        print('Target content: ', target_content)
        if chosen_content != 'Select...':
            target_content = content_analyzer_samples_folder+target_content
            file_path_tokens = target_content.split('/')
            local_file = file_path_tokens[len(file_path_tokens) - 1]
            s3.download_file(s3_bucket, target_content, local_file)
        #else:
        #    local_file = uploaded_img.name
        #    s3.download_file(s3_bucket, s3_prefix+'/'+uploaded_img.name, uploaded_img.name)
            
        if file_type not in ['py','java','ipynb','pdf']:
            contents = textract.process(local_file).decode('utf-8')
            new_contents = contents[:chunk].replace('$','\$')
        elif file_type == 'pdf':
            contents = readpdf(local_file)
            new_contents = contents[:chunk].replace("$","\$")
        else:
            with open(local_file, 'rb') as f:
                contents = f.read()
            new_contents = contents[:chunk].decode('utf-8')


        #print('New uploaded contents from session: ', new_contents)
        
        # lang = comprehend.detect_dominant_language(Text=new_contents)
        # lang_code = str(lang['Languages'][0]['LanguageCode']).split('-')[0]
        # if lang_code in ['en']:
        #     resp_pii = comprehend.detect_pii_entities(Text=new_contents, LanguageCode=lang_code)
        #     immut_summary = new_contents
        #     for pii in resp_pii['Entities']:
        #         if pii['Type'] not in ['NAME', 'AGE', 'ADDRESS','DATE_TIME']:
        #             pii_value = immut_summary[pii['BeginOffset']:pii['EndOffset']]
        #             new_contents = new_contents.replace(pii_value, str('PII - '+pii['Type']))

        result = GetAnswers(new_contents,input_text)
        result = result.replace("$","\$")
        st.write(result)              

st.sidebar.markdown('### :red[Cost of Invocations] \n' 
                + gen_ai_selector.report_cost())
