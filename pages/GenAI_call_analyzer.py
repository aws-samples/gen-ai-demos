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
import pandas as pd
import uuid
import os
import time
from utils import gen_ai_selector
from utils import cognito_helper

import pages.imports.sts_assume_role as boto3_session

key = os.environ['AWS_ACCESS_KEY_ID']
secret = os.environ['AWS_SECRET_ACCESS_KEY']
region = os.environ['AWS_DEFAULT_REGION']

autorefresh_session = boto3_session.run_autorefresh_session()
comprehend = autorefresh_session.client('comprehend')
bedrock = autorefresh_session.client('bedrock')

st.set_page_config(page_title="GenAI Call Analyzer", page_icon="headphones")

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
    - Use these selection of [samples for playing with the demos](https://github.com/aws-samples/gen-ai-samples/sample-artifacts). 
    - The demos should not be considered as an actual prototype or working version of a proposed solution
    """)


if 'full_transcript' not in st.session_state:
    st.session_state['full_transcript'] = None
if 'turn_df' not in st.session_state:
    st.session_state['turn_df'] = pd.DataFrame()
if 'call_df' not in st.session_state:
    st.session_state['call_df'] = pd.DataFrame()
if 'model_summary' not in st.session_state:
    st.session_state['model_summary'] = None


s3 = boto3.client('s3',region_name=region,aws_access_key_id=key,aws_secret_access_key=secret)
comprehend = boto3.client('comprehend',region_name=region,aws_access_key_id=key,aws_secret_access_key=secret)
transcribe = boto3.client("transcribe",region_name=region,aws_access_key_id=key,aws_secret_access_key=secret)

# Get environment variables
iam_role = os.environ['IAM_ROLE']
bucket = os.environ['bucket']
model_summary = ''
languages = ['English', 'Spanish', 'German', 'Portugese', 'Irish', 'Star Trek - Klingon', 'Star Trek - Ferengi', 'Italian', 'French', 'Japanese', 'Mandarin', 'Tamil', 'Hindi', 'Telugu', 'Kannada', 'Arabic', 'Hebrew']
default_lang = languages.index('English')
icols = ['job', 'turn','content', 'participant_role', 'loudness_score']
turn_df = pd.DataFrame(columns=icols)
ocols = ['job', 'non-talk-instances', 'non-talk-time', 'interruption_count', 'interruption_tot_duration', 'total_conv_duration']
call_df = pd.DataFrame(columns=ocols)

paginator = s3.get_paginator('list_objects_v2')
call_content_entries = paginator.paginate(Bucket=bucket)
media_files = ['Select...']

for call_content_entry_page in call_content_entries:
    for call_content_entry in call_content_entry_page['Contents']:
        entry = call_content_entry['Key']
        if "call-analyzer" in entry.lower():
            mf = entry.split('/')[1]
            if mf != '' and ( entry.endswith('.wav') or entry.endswith('.mp3') or entry.endswith('.mp4')):
                media_files.append(mf)


st.markdown("# Call Analytics and Insights")
st.sidebar.header("GenAI Call Analyzer")
st.sidebar.markdown('''
        ### Example prompts for the transcript \n\n
        How could the overall experience be improved? \n
        Did the agent resolve the customer's request? \n
        What could the agent have done better? \n
        What can the agent upsell or cross-sell to the customer? \n
    ''')

genai_models = gen_ai_selector.genai_models
default_model = gen_ai_selector.default_genai_model_index
model = st.sidebar.selectbox('Select a FM', genai_models, index=default_model)

models = gen_ai_selector.genai_model_functions


def call_models(full_transcript, command, query):
    func = models[model]['func']
    generated_text = func(full_transcript+'. '+command+query.lower())
    answer = None
    
    if generated_text != '':
        answer = str(generated_text) 
        answer = answer.replace("$","\$")
    else:
        answer = 'Sorry!! did not find an answer to your question, please try again'
    return answer
    
def GetAnswers(full_transcript,query):
    model_response = call_models(full_transcript, 'Answer neutrally without bias from this text:',query)             
    return model_response



# Method to run Transcribe call analytics
def runCallAnalytics(job_name, job_uri, output_location):
    try:
        transcribe.start_call_analytics_job(
             CallAnalyticsJobName = job_name,
             Media = {
                'MediaFileUri': job_uri
             },
             DataAccessRoleArn = iam_role,
             OutputLocation = output_location,
             ChannelDefinitions = [
                {
                    'ChannelId': 1, 
                    'ParticipantRole': 'AGENT'
                },
                {
                    'ChannelId': 0, 
                    'ParticipantRole': 'CUSTOMER'
                }
             ]
         )
        time.sleep(2)
        st.success("Transcribe Call analytics job submitted")        
    except Exception as e:
        print(e)

#upload audio file to S3 bucket
def upload_audio_start_transcript(bytes_data, bucket, s3_file):
    output_prefix = 'streamlit_transcripts'
    s3.upload_fileobj(bytes_data, bucket, s3_file)
    st.success('Audio uploaded')
    #paginator = s3.get_paginator('list_objects_v2')
    #pages = paginator.paginate(Bucket=bucket, Prefix='streamlit_audio')
    job_name_list = []
    output_location = f"s3://{bucket}/{output_prefix}/"
    #for page in pages:
    #    for obj in page['Contents']:
    random = str(uuid.uuid4())
    audio_name = bytes_data.name
    job_name = audio_name + '-' + random
    job_name_list.append(job_name)
    job_uri = f"s3://{bucket}/{s3_file}"
    st.success('Submitting Amazon Transcribe call analytics for your audio: ' + job_name)
    
    # submit the transcription job now, we will provide our current bucket name as the output bucket
    runCallAnalytics(job_name, job_uri, output_location)
    return job_name_list

def upload_segments(job, i, transcript):
    # Get the turn by turn contents
    turn_idx = 0
    idx = len(turn_df)
    full_transcript = ""
    for turn in transcript['Transcript']:
        idx += 1
        turn_idx += 1
        # Build the base dataframe of call details, sentiment and loudness
        turn_df.at[idx,'job'] = job
        turn_df.at[idx, 'turn'] = turn_idx
        turn_df.at[idx,'content'] = str(turn['Content']).replace("'","").replace(",","")
        turn_df.at[idx, 'participant_role'] = turn['ParticipantRole']
        turn_df.at[idx, 'sentiment'] = turn['Sentiment']
        full_transcript += turn['Content']
        
        # Get an average loudness score for each turn
        tot_loud = 0
        for loud in turn['LoudnessScores']:
            if loud is not None:
                tot_loud += int(loud)
        avg_loudness = tot_loud/len(turn['LoudnessScores'])
        turn_df.at[idx, 'loudness_score'] = round(avg_loudness,0)
    
    # Finally get the overall call characteristics into a seperate dataframe
    call_df.at[i,'job'] = job
    call_df.at[i,'non-talk-instances'] = len(transcript['ConversationCharacteristics']['NonTalkTime']['Instances'])
    call_df.at[i,'non-talk-time'] = transcript['ConversationCharacteristics']['NonTalkTime']['TotalTimeMillis']
    call_df.at[i, 'interruption_count'] = transcript['ConversationCharacteristics']['Interruptions']['TotalCount']
    call_df.at[i, 'interruption_tot_duration'] = transcript['ConversationCharacteristics']['Interruptions']['TotalTimeMillis']
    call_df.at[i, 'total_conv_duration'] = transcript['ConversationCharacteristics']['TotalConversationDurationMillis']
    return full_transcript

def start_transcript(chosen_audio):
    output_prefix = 'streamlit_transcripts'
    job_name_list = []
    print('Chosen audio: ', chosen_audio)
    output_location = f"s3://{bucket}/{output_prefix}/"
    random = str(uuid.uuid4())
    
    file_path_tokens = chosen_audio.split('/')
    job_name = file_path_tokens[len(file_path_tokens) - 1] + '-' + random
    job_name_list.append(job_name)
    #job_uri = f"s3://{bucket}/{output_prefix}/{chosen_audio}"
    job_uri = f"s3://{bucket}/{chosen_audio}"
    print('job uri:' , job_uri)
    runCallAnalytics(job_name, job_uri, output_location)
    return job_name_list

st.write("**Instructions:** \n " \
         "1. Select an output language. \n" \
         "2. Select your sample contact center audio file from available list or upload your own audio content. \n" \
         "3. You will see call analytics and summary generated. \n" \
         "4. Type your queries in the search bar to get conversation insights")



#st.markdown('`Going with pre-available sample audio content!!`')
c1, c2 = st.columns(2)

c1.subheader('Select sample call recording')
chosen_audio_select = c1.selectbox(
    'Select a sample recording',
        media_files
    )

c2.subheader("Select an output language")
language = c2.selectbox(
    'Select an output language from list of available options.',
    options=languages, index=default_lang)


full_transcript = ''
job_name_list = []

if chosen_audio_select != "Select...":
    if st.button("Submit"):
        with st.spinner('Uploading audio file and starting Amazon Transcribe call analytics...'):
            print('Chose audio? : ', chosen_audio_select)
            job_name_list = start_transcript('call-analyzer-samples/'+chosen_audio_select)


if len(job_name_list) > 0:
    st.session_state.full_transcript = None
    st.session_state.turn_df = pd.DataFrame()
    st.session_state.call_df = pd.DataFrame()
    st.session_state.model_summary = None
    with st.spinner('Awaiting call analytics job completion...'): 
        finish = False
        st.markdown("This should take a couple of minutes. Please check out these [great features of Amazon Transcribe](https://aws.amazon.com/transcribe/features/) in the meanwhile...")
        while finish == False:
            time.sleep(30)
            response = transcribe.get_call_analytics_job(CallAnalyticsJobName=job_name_list[0])
            job_status = response['CallAnalyticsJob']['CallAnalyticsJobStatus']
            st.write("Status of your call analytics job is: " + job_status)
            if job_status.upper() == 'COMPLETED':
                st.success("Call analytics job status: " + job_status)
                finish = True
                break
            elif job_status.upper() == 'FAILED':
                st.write('Failure with transcribe: ' + str(response))
                print(response)
                finish = True
                break
                
    # First we need an output directory
    dir = os.getcwd()+'/transcript_output'
    if not os.path.exists(dir):
        os.makedirs(dir)            

    # Get Call Analytics output
    i = -1
    for job in job_name_list:
        response = transcribe.get_call_analytics_job(CallAnalyticsJobName=job)
        json_file = response['CallAnalyticsJob']['Transcript']['TranscriptFileUri']
        a = json_file.split('/')
        tca_prefix = '/'.join(a[4:])
        s3.download_file(bucket,tca_prefix,dir+'/'+job)
        with open(dir+'/'+job) as f:
            data = json.load(f)
        i += 1
        full_transcript = upload_segments(str(job), i, data)
    st.session_state['full_transcript'] = full_transcript   
    model_summary = call_models(full_transcript, 'Summarize this text to 100 words in '+language+':',query='')
    model_summary = model_summary.replace("$","\$")
    lang = comprehend.detect_dominant_language(Text=model_summary)
    lang_code = str(lang['Languages'][0]['LanguageCode']).split('-')[0]
    if lang_code in ['en']:
        resp_pii = comprehend.detect_pii_entities(Text=model_summary, LanguageCode=lang_code)
        immut_summary = model_summary
        for pii in resp_pii['Entities']:
            #if pii['Type'] not in ['ADDRESS','DATE_TIME']:
            pii_value = immut_summary[pii['BeginOffset']:pii['EndOffset']]
            model_summary = model_summary.replace(pii_value, str('PII - '+pii['Type']))



if st.session_state.full_transcript == None:
    st.session_state['full_transcript'] = full_transcript
if st.session_state.model_summary == None:
    st.session_state['model_summary'] = model_summary
if st.session_state.turn_df.empty:
    st.session_state.turn_df = pd.DataFrame(turn_df)
if st.session_state.call_df.empty:
    st.session_state.call_df = pd.DataFrame(call_df)

#display turn by turn
if not st.session_state.turn_df.empty:
    st.write("**Turn by turn sentiment** \n")
    st.bar_chart(st.session_state.turn_df[['sentiment']])
    #st.dataframe(st.session_state.turn_df, use_container_width=True)

#display call header
if not st.session_state.call_df.empty:
    st.write("**Call analytics** \n")
    st.table(st.session_state.call_df)

p_summary = None
if st.session_state.model_summary:
    st.write('**Transcript Summary** \n') 
    st.write(st.session_state['model_summary'])
    #if model == 'anthropic claude':  
    func = models[model]['func']
    p_text = func('Generate three prompts to query the summary: '+ st.session_state.model_summary)
    p_text1 = []
    p_text2 = ''
    if p_text is not None and p_text != '':
        p_text = p_text.replace("$","\$")
        p_text1 = p_text.split('\n')
        for i,t in enumerate(p_text1):
            if i > 1:
                p_text2 += t.split('?')[0]+'\n\n'
            else:
                p_text2 += t + '\n\n'                
        p_summary = p_text2
    else:
        p_summary = '''
        1. How could the overall experience be improved? \n
        2. Did the agent resolve the customer's request? \n
        3. What could the agent have done better? \n
        '''  
    st.sidebar.markdown('### Suggested prompts for further insights \n\n' + 
            p_summary)

resp_pii = []
pii_list = []
pii_value = ''

if st.session_state.full_transcript:
    input_text = st.text_input('**What conversation insights would you like?**', key='text_ca')
    if input_text != '':
        result = GetAnswers(st.session_state.full_transcript,input_text)
        result = result.replace("$","\$")
        st.write(result)
        #resp_pii = comprehend.detect_pii_entities(Text=result, LanguageCode='en')
        #immut_result = result
        #for pii in resp_pii['Entities']:
            #if pii['Type'] not in ['ADDRESS','DATE_TIME']:
        #    pii_value = immut_result[pii['BeginOffset']:pii['EndOffset']]
        #    result = result.replace(pii_value, str('PII - '+pii['Type']))
        #st.write(result)

st.sidebar.markdown('### :red[Cost of Invocations] \n' 
                + gen_ai_selector.report_cost())
