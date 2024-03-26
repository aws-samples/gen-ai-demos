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
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
import base64
import uuid
import os
import sagemaker
from sagemaker import ModelPackage, get_execution_role
from stability_sdk_sagemaker.predictor import StabilityPredictor
from stability_sdk_sagemaker.models import get_model_package_arn
from stability_sdk.api import GenerationRequest, GenerationResponse, TextPrompt
from PIL import Image
import io
import base64
import random
from utils import gen_ai_selector
from utils import cognito_helper

import pages.imports.sts_assume_role as boto3_session

autorefresh_session = boto3_session.run_autorefresh_session()

s3 = autorefresh_session.client('s3')
comprehend = autorefresh_session.client('comprehend')
rekognition = autorefresh_session.client('rekognition')
kendra = autorefresh_session.client("kendra")
textract = autorefresh_session.client("textract")

iam_role = os.environ['IAM_ROLE']

# Get environment variables
bucket = os.environ['bucket']
im_endpoint_name = os.environ['im_endpoint_name']
tx_endpoint_name = os.environ['tx_endpoint_name']

# Get environment variables
languages = ['English', 'Spanish', 'German', 'Portugese', 'Irish', 'Korean', 'Swedish', 'Norwegian', 'Danish', 'Icelandic', 'Finnish', 'Star Trek - Klingon', 'Star Trek - Ferengi', 'Italian', 'French', 'Japanese', 'Mandarin', 'Tamil', 'Hindi', 'Telugu', 'Kannada', 'Arabic', 'Hebrew']

negative_prompt = (
    "ugly, tiling, poorly drawn hands, poorly drawn face, out of frame, extra limbs, \
    disfigured, deformed, body out of frame, bad anatomy, watermark, signature, cut off, \
    low quality, bad art, beginner, windy, amateur, distorted face, blurry, blurred, grainy, \
    draft, low contrast, underexposed, overexposed"
)

wallpaper_height=512
wallpaper_width=512

random_seed = random.randint(1,1000000000)

available_style_presets = [
    "anime",
    "photographic",
    "digital-art",
    "comic-book",
    "fantasy-art",
    "line-art",
    "analog-film",
    "neon-punk",
    "isometric",
    "low-poly",
    "origami",
    "modeling-compound",
    "cinematic",
    "3d-model",
    "pixel-art",
    "tile-texture",
]

st.set_page_config(page_title="GenAI Product Ideator", page_icon="high_brightness")

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
st.markdown("# Take your product idea to the next level")
st.sidebar.header("GenAI product ideator")
st.sidebar.markdown("### Make your pick")

default_style = available_style_presets.index('3d-model')

wallpaper_style = st.sidebar.selectbox("Wallpaper Style Presets", available_style_presets, index=default_style)


industry = ''
industry = st.sidebar.selectbox(
    'Select an industry',
    ('Retail', 'Fashion', 'Manufacturing', 'Technology', 'Transport'))



genai_models = gen_ai_selector.genai_models
default_model = gen_ai_selector.default_genai_model_index
model = st.sidebar.selectbox('Select a FM', genai_models, index=default_model)

models = gen_ai_selector.genai_model_functions

img_models = {
    "bedrock" : gen_ai_selector.find_bedrock_model('bedrock sdxl'),
    #"jumpstart" : gen_ai_selector.find_jumpstart_model('sdxl')
}




def call_sdxl(query):
    #output = deployed_model.predict(GenerationRequest(text_prompts=[TextPrompt(text=query)],
    
    prompt_text = query
    
    chosen_type = 'bedrock sdxl' if model.startswith('bedrock') else 'jumpstart sdxl'
    sd_model = gen_ai_selector.find_bedrock_model('bedrock sdxl')
    img_func = sd_model['func']
    
    output = img_func(prompt_text,
                     style_preset="digital-art",
                     seed = 1885337276,
                     steps=100,
                     cfg_scale=10,
                     image_strength=0.5
                     )
    return output

def sdxl_decode_and_show(model_response: GenerationResponse) -> None:
    """
    Decodes and displays an image from SDXL output

    Args:
        model_response (GenerationResponse): The response object from the deployed SDXL model.

    Returns:
        None
    """
    artifacts = model_response['artifacts']
    image = artifacts[0]['base64']
    image_data = base64.b64decode(image.encode())
    image = Image.open(io.BytesIO(image_data))
    return image


#def query_im_endpoint(text):
#    client = boto3.client('runtime.sagemaker')
#    payload = {
#    "prompt": text,
#    "width": 480,
#    "height": 480,
#    "num_inference_steps": 200,
#    "seed": 42,
#    "guidance_scale": 8.5
#    }
#    body = json.dumps(payload).encode('utf-8')
#    response = client.invoke_endpoint(EndpointName=im_endpoint_name, ContentType='application/json', Body=body, Accept='application/json;jpeg')

#    return response

def parse_im_response(query_im_response):
    response_dict = json.loads(query_im_response['Body'].read())
    return response_dict['generated_images'], response_dict['prompt']

def save_image(img, prmpt):
    plt.figure(figsize=(12,12))
    plt.imshow(np.array(img))
    plt.axis('off')
    plt.title(prmpt)
    prefix = "test-"+str(uuid.uuid4())+".jpg"
    plt.savefig("/tmp/"+prefix)
    #print("image name before S3 upload is: " + "/tmp/"+prefix)
    s3.upload_file("/tmp/"+prefix, bucket, prefix)
    img_url = 'http://dzlvehx4kcg5h.cloudfront.net/'+prefix
    return img_url

def GetAnswers(query):
    pii_list = []
    answer = None
    
    #sentiment = comprehend.detect_sentiment(Text=query, LanguageCode='en')['Sentiment']
    resp_pii = comprehend.detect_pii_entities(Text=query, LanguageCode='en')
    for pii in resp_pii['Entities']:
        if pii['Type'] not in ['NAME', 'AGE', 'ADDRESS','DATE_TIME']:
            pii_list.append(pii['Type'])
    if len(pii_list) > 0:
        answer = "I am sorry but I found PII entities " + str(pii_list) + " in your query. Please remove PII entities and try again."
        return answer
    query_type = ''
    
    if query == "cancel":
        answer = 'It was swell interacting with you. Thanks for your time.'
        return answer
    else:
        # Call the Stability model to get the image for our query, save it in S3 and build a response card
        #response = query_im_endpoint("Detailed image of " + query+" in " + industry.lower())
        #timg, prmpt = parse_im_response(response)
        #generated_image_decoded = BytesIO(base64.b64decode(timg[0].encode()))
        #generated_image_rgb = Image.open(generated_image_decoded).convert("RGB")
        #img_url_new = save_image(generated_image_rgb, prmpt)
        st.write("**Example image for your product idea**: \n")
        sd_query = "Generate a detailed image of " + query+" in " + industry.lower() 
        st.image(sdxl_decode_and_show(call_sdxl(sd_query)))
        #st.image(img_url_new)
        generated_text = ''
        prompt_text = 'Create a product description in '+language+' in 200 words for '+ query.strip("query:")
        func = models[model]['func']
        answer = func(prompt_text)
        answer = answer.replace("$","\$")   
        return answer                       

st.write("**Instructions:** \n - Type a product idea prompt \n - You will see an image, a product description, and press release generated for your product idea")


input_text = st.text_input('**What is your product idea?**', key='prod_text')
default_lang_ix = languages.index('English')
language = st.selectbox(
    '**Select an output language.** Only Alpha and Beta quadrant languages supported. For new requests, please contact C-3PO',
    options=languages, index=default_lang_ix)
key_phrases = ''
answer = None
if input_text != '':
    result = GetAnswers(input_text)
    result = result.replace("$","\$")
    tab1, tab2, tab3, tab4 = st.tabs(["Product description", "Internal memo", "Press release", "Social Media Ad"])
    #c1, c2 = st.columns(2)
    with tab1:
        st.write("**Description for your product idea**")
        st.write(result)
    with tab2:
        st.write("**Internal memo for your product idea**")
        prompt_text = 'Generate an internal memo announcing the launch decision in '+language+' for '+ input_text.strip("query:")
        func = models[model]['func']
        answer = func(prompt_text)
        answer = answer.replace("$","\$") 
        st.write(answer)
    with tab3:
        st.write("**Press release for your product idea**")
        prompt_text = 'Generate a press release and some FAQs to help understand the product better in '+language+' for '+ input_text.strip("query:")
        func = models[model]['func']
        answer = func(prompt_text)
        answer = answer.replace("$","\$") 
        st.write(answer)
    with tab4:
        st.write("**Social Media Ad for your product idea**")
        prompt_text = 'Generate a catchy trendy social media ad in '+language+' for '+ input_text.strip("query:")
        func = models[model]['func']
        answer = func(prompt_text)
        answer = answer.replace("$","\$") 
        st.write(answer)
        st.balloons()
    
st.sidebar.markdown('### :red[Cost of Bedrock Invocations] \n' 
                + gen_ai_selector.report_cost())
