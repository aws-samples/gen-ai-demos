import streamlit as st
import streamlit_scrollable_textbox as stx
import json
import os

import subprocess
from utils import gen_ai_selector

from pathlib import Path
from streamlit.source_util import _on_pages_changed, get_pages


def run_and_display_stdout(*cmd_with_args):
  result = subprocess.Popen(cmd_with_args, stdout=subprocess.PIPE)
  for line in iter(lambda: result.stdout.readline(), b""):
     st.text(line.decode("utf-8"))

debug_enabled = os.environ.get('ENV_DEBUG1')
if debug_enabled != None:
    run_and_display_stdout("env")

if 'accepted' not in st.session_state:
    st.session_state['accepted'] = 'False'

DEFAULT_PAGE = "App.py"

st.set_page_config(
    page_title="AWS GenAI Demo Showcase",
    page_icon="crystall_ball",
)

from utils import cognito_helper

def get_all_pages():
    default_pages = get_pages(DEFAULT_PAGE)

    pages_path = Path("pages.json")

    if pages_path.exists():
        saved_default_pages = json.loads(pages_path.read_text())
    else:
        saved_default_pages = default_pages.copy()
        pages_path.write_text(json.dumps(default_pages, indent=4))

    return saved_default_pages


def clear_all_but_first_page():
    current_pages = get_pages(DEFAULT_PAGE)

    if len(current_pages.keys()) == 1:
        return

    get_all_pages()

    # Remove all but the first page
    key, val = list(current_pages.items())[0]
    current_pages.clear()
    current_pages[key] = val

    _on_pages_changed.send()


def show_all_pages():
    current_pages = get_pages(DEFAULT_PAGE)
    saved_pages = get_all_pages()
    missing_keys = set(saved_pages.keys()) - set(current_pages.keys())

    # Replace all the missing pages
    for key in missing_keys:
        current_pages[key] = saved_pages[key]

    _on_pages_changed.send()


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
    
show_all_pages()        
with st.sidebar:
    st.text(f"Welcome,\n{cognito_helper.getuser()}")
    st.button("Logout", on_click=cognito_helper.logout)

welcome_msg = cognito_helper.get_welcome_msg()

st.markdown(
    """
    ### :red[Note] 
    - These demos are for informational purposes only.
    - Use these selection of [samples for playing with the demos](https://github.com/aws-samples/gen-ai-samples/sample-artifacts). 
    - The demos should not be considered as an actual prototype or working version of a proposed solution
    """)

st.write("# :green[Welcome to the AWS Generative AI Demo Showcase!]")
st.write(f"##### :green[" + welcome_msg + "]")

tab1, tab2, tab3 = st.tabs(["Industry", "Usecase", "Function"])

with tab1:
    industry = st.selectbox(
        '**Select an industry to begin**',
        ('Select...', 'Automotive', 'Financial Services', 'Healthcare', 'Hospitality', 'Life Sciences', 'Legal', 'Manufacturing', 'Energy', 'Retail', 'Technology', 'Transport', 'Fashion'))

    if industry == 'Automotive':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, csv or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')
    elif industry == 'Energy':
        st.markdown('''
            ### Available demos
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, csv or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Enterprise Search](/GenAI_enterprise_search_interpreter):** Intelligent enterprise search, auto-prompts and conversational interpretation using Amazon Kendra and a LLM \n
        ''')   
    elif industry == 'Financial Services':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, csv or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Enterprise Search](/GenAI_enterprise_search_interpreter):** Intelligent enterprise search, auto-prompts and conversational interpretation using Amazon Kendra and a LLM \n
        ''')
    elif industry == 'Healthcare':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML, or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')
    elif industry == 'Hospitality':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML, or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')
    elif industry == 'Legal':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML,  or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Enterprise Search](/GenAI_enterprise_search_interpreter):** Intelligent enterprise search, auto-prompts and conversational interpretation using Amazon Kendra and a LLM \n
        ''')
    elif industry == 'Life Sciences':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML,  or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            
        ''')
    if industry == 'Manufacturing':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, csv or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')
    elif industry == 'Fashion':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML,  or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Product Ideator](/GenAI_product_ideator):** Create product images, description and a press release with just a few words \n
        ''')
    elif industry == 'Retail':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML, or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Product Ideator](/GenAI_product_ideator):** Create product images, description and a press release with just a few words \n
            - **[GenAI Sales Accelerator](/SalesAccelerator):** Analysis of image, description and summarization \n
        ''')
    elif industry == 'Transport':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML,  or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Product Ideator](/GenAI_product_ideator):** Create product images, description and a press release with just a few words \n
        ''')
    elif industry == 'Technology':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML, or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Product Ideator](/GenAI_product_ideator):** Create product images, description and a press release with just a few words \n
        ''')
with tab2:
    usecase = st.selectbox(
        '**Select an usecase to begin**',
        ('Select...', 'Customer Experience', 'Productivity Improvement', 'Document Processing', 'Enterprise Search', 'Content Generation'))

    if usecase == 'Customer Experience':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            
        ''')
    elif usecase == 'Productivity Improvement':
        st.markdown('''
            ### Available demos
            - **[GenAI Agile Guru](/GenAI_Agile_Guru):** Generate Agile Sprint artifacts in seconds \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, csv or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')   
    elif usecase == 'Document Processing':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, csv or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')
    elif usecase == 'Enterprise Search':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Enterprise Search](/GenAI_enterprise_search_interpreter):** Intelligent enterprise search, auto-prompts and conversational interpretation using Amazon Kendra and a LLM \n
        ''')
    elif usecase == 'Content Generation':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Agile Guru](/GenAI_Agile_Guru):** Generate Agile Sprint artifacts in seconds \n
            - **[GenAI Product Ideator](/GenAI_product_ideator):** Create product images, description and a press release with just a few words \n
        ''')
with tab3:
    function = st.selectbox(
        '**Select a job function to begin**',
        ('Select...', 'Research & Development', 'Product Management', 'Sales & Marketing', 'Engineering', 'Content Analysis', 'Management'))

    if function == 'Research & Development':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Agile Guru](/GenAI_Agile_Guru):** Generate Agile Sprint artifacts in seconds \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, csv or text files, get a summary, auto-prompts and conversational insights using an LLM \n
            - **[GenAI Enterprise Search](/GenAI_enterprise_search_interpreter):** Intelligent enterprise search, auto-prompts and conversational interpretation using Amazon Kendra and a LLM \n
        ''')
    elif function == 'Product Management':
        st.markdown('''
            ### Available demos
            - **[GenAI Product Ideator](/GenAI_product_ideator):** Create product images, description and a press release with just a few words \n
        ''')   
    elif function == 'Sales & Marketing':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Enterprise Search](/GenAI_enterprise_search_interpreter):** Intelligent enterprise search, auto-prompts and conversational interpretation using Amazon Kendra and a LLM \n
            - **[GenAI Product Ideator](/GenAI_product_ideator):** Create product images, description and a press release with just a few words \n
        ''')
    elif function == 'Engineering':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Agile Guru](/GenAI_Agile_Guru):** Generate Agile Sprint artifacts in seconds \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML, or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')
    elif function == 'Content Analysis':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI Call Analyzer](/GenAI_call_analyzer):** Call transcription, analytics, summarization, auto-prompts and conversational insights using Amazon Transcribe and a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML, or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
        ''')
    elif function == 'Management':
        st.markdown('''
            ### Available demos \n\n
            - **[GenAI ChatAway](/GenAI_ChatAway):** Conversational chat-style interaction using a LLM \n
            - **[GenAI Content Analyzer](/GenAI_content_analyzer):** Upload images, MS Word, Excel, PPT, PDF, CSV, HTML,  or text files, get a summary, auto-prompts and conversational insights using Amazom Rekognition and a LLM \n
            - **[GenAI Enterprise Search](/GenAI_enterprise_search_interpreter):** Intelligent enterprise search, auto-prompts and conversational interpretation using Amazon Kendra and a LLM \n
        ''')

st.markdown(
    """
    Learn the Generative AI art-of-the-possible with these awesome demos for popular use cases!
    Using a combination of purpose built AWS AI services with powerful LLMs you can go from ideation to implementation in **a few minutes!!**
    Be ready to be wowed!!
    
    - [How did we make these awesome demos](/GenAI_Demo_Reference_Architectures)

    ### Learn more about AWS AI services
    
    - [Pre-trained AI services](https://aws.amazon.com/machine-learning/ai-services/)
    - [AI usecases explorer](https://aiexplorer.aws.amazon.com/?lang=en&trk=47702943-c5e6-44e8-841f-d061a5468505&sc_channel=el)
   
    ### Learn more about AWS Generative AI announcements

    - [Amazon Bedrock](https://aws.amazon.com/bedrock/)
    - [Amazon CodeWhisperer](https://aws.amazon.com/codewhisperer/)
    - AWS Accelerated Computing [training](https://aws.amazon.com/blogs/aws/amazon-ec2-trn1-instances-for-high-performance-model-training-are-now-available/) and [inference for Generative AI](https://aws.amazon.com/blogs/aws/amazon-ec2-inf2-instances-for-low-cost-high-performance-generative-ai-inference-are-now-generally-available)


    """
)



