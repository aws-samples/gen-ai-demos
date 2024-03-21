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

# This utility is to parse AI21 sageamkaer relaeted files from the public AI21 github repo (https://github.com/AI21Labs/SageMaker
# to pull Sagemaker related Model ARN and recommended instance type (or first provided instance type for inference)
# The parsed content is already saved as a json file (ai21_model_package_arns.json) for quick reference

from github import Github
import os
import requests
import re
import json


ai21_map = {}

LOCAL_FILE_REPO = '/home/ec2-user/environment/workspace/AI21-SM/'

REPO = "AI21Labs/SageMaker"
FULL_REPO = f'https://github.com/{REPO}'
RAW_FULL_REPO = f'https://raw.githubusercontent.com/{REPO}'

def check_sagemaker_arns_and_instance(filePath):
    #print( 'Processing raw file: ' + f'{RAW_FULL_REPO}/main/{filePath}')
    content = requests.get(f'{RAW_FULL_REPO}/main/{filePath}', stream=True)
    
    arn_entries = {}
    instance_type = ''
    
    recommended_instance = None
    for line in content.iter_lines():
        line_str = str(line)
        #print(line_str)
        
        if 'arn:aws:sagemaker' in line_str:
            start = line_str.index('\\')
            len_str = len(line_str)
            end = line_str.index('\\', len_str - 10)
            arn_entry = line_str[start:end+3].replace('\\', '')
            #print(arn_entry)
            index = arn_entry.index(':')
            region = arn_entry[0:index - 1].replace('"', '')
            arn_entries[region] = arn_entry[index+1:].replace('"', '').replace(',', '').strip()
            #print('arn path: ', arn_entry[index+1:])
        elif 'Recommended instance' in line_str:
            #print(line_str)
            recommended_instance = line_str
        elif '"instance_type"' in line_str:
            #print(line_str)
            instance_type = line_str
     
    if recommended_instance != None:
        instance_type = recommended_instance
    
    instance_type = re.sub('# .*', '', instance_type).replace('\\', '').replace('b\'', '').replace('"', '').replace(',', '').strip()
    #print('Final Instnace type:', instance_type)        
            
    #print(arn_entries)
    #print(instance_type)
        
    final_model_package = { 'model_package_map': arn_entries, 'instance_type': instance_type } 
    return final_model_package

def check_local(filePath):
    #print('checking local file:', filePath) 
    file1 = open(filePath, 'r')
    lines = file1.readlines()
    
    arn_entries = {}
    instance_type = ''    
    
    recommended_instance = None
    for line in lines:
        line_str = str(line)
        if 'arn:aws:sagemaker' in line_str:
            start = line_str.index('\\')
            len_str = len(line_str)
            end = line_str.index('\\', len_str - 10)
            arn_entry = line_str[start:end+3].replace('\\n', '').replace('\\', '')
            #print(arn_entry)
            index = arn_entry.index(':')
            region = arn_entry[0:index - 1].replace('"', '')
            arn_entries[region] = arn_entry[index+1:].replace('"', '').replace(',', '').strip()
            #print('arn path: ', arn_entry[index+1:])
        elif 'Recommended instance' in line_str:
            #print(line_str)
            recommended_instance = line_str
        elif ( 'ml' in line_str and 'large' in line_str and instance_type == '' ):
            instance_type = line_str
            #instance_type = re.sub('# .*', '', line_str).replace('\\n', '').replace('\\', '').replace('"', '').replace(',', '').strip()
            #print(instance_type)
            
    if recommended_instance != None:
        instance_type = recommended_instance
    
    instance_type = re.sub('# .*', '', instance_type).replace('\\n', '').replace('\\', '').replace('"', '').replace(',', '').strip()
    #print('Recommended Instance type:', instance_type)        
            
    #print(arn_entries)
    #print(instance_type)
        
    final_model_package = { 'model_package_map': arn_entries, 'instance_type': instance_type } 
    return final_model_package

def create_model_package_map_from_github():
    g = Github()
    repo = g.get_repo(REPO)
    
    for file in repo.get_contents("."):
        #print(file.name)
        if ('.ipynb' in file.name):
            model_name = 'ai21.' + file.lower().replace('_example_model_use.ipynb', '').replace('_', '-')
            model_map_entry = { 'model': model_name, 'model_package_map': [ ] }
            parsed_package_map = check_sagemaker_arns_and_instance(file.name)
            if len(parsed_package_map['model_package_map']) != 0:
                model_map_entry['model_package_map'] = parsed_package_map['model_package_map']
                model_map_entry['instance_type'] = parsed_package_map['instance_type']
                ai21_map[model_name] = model_map_entry
    
    return ai21_map
    
# For local file testing
def create_model_package_map_from_local_files():
    for file in [ 
          'AI21_ContextualAnswers_example_model_use.ipynb',  'AI21_Summarize_example_model_use.ipynb',  'J2_GrandeInstruct_example_model_use.ipynb',  'J2_Large_example_model_use.ipynb',  'J2_Ultra_example_model_use.ipynb',
          'AI21_GEC_example_model_use.ipynb',                'J1_Grande_example_model_use.ipynb',       'J2_Jumbo_example_model_use.ipynb',           'J2_Light_example_model_use.ipynb',
          'AI21_Paraphrase_example_model_use.ipynb',         'J2_Grande_example_model_use.ipynb',       'J2_JumboInstruct_example_model_use.ipynb',   'J2_Mid_example_model_use.ipynb' ]:
        #print(file)
        model_name = 'ai21.' + file.lower().replace('_example_model_use.ipynb', '').replace('_', '-')
        model_map_entry = { 'model': model_name, 'model_package_map': [ ] }
        #check_sagemaker_arns_and_instance(file.name
        parsed_package_map = check_local(LOCAL_FILE_REPO + file)
        if len(parsed_package_map['model_package_map']) != 0:
            model_map_entry['model_package_map'] = parsed_package_map['model_package_map']
            model_map_entry['instance_type'] = parsed_package_map['instance_type']
            ai21_map[model_name] = model_map_entry
        
    return ai21_map


#create_model_package_map_from_github()
create_model_package_map_from_local_files()
#print(ai21_map)
print()
#print(json.dumps(ai21_map))
#exit(-1)

# Test
script_dir = os.path.dirname(__file__) #<-- absolute dir the script is in
ai21_model_package_defn = 'ai21_model_package_arns.json'
ai21_model_package_path = os.path.join(script_dir, ai21_model_package_defn)
model_package_file = open(ai21_model_package_path)
ai21_model_package_json = json.load(model_package_file)
print('loaded json:')

model_id='ai21.j1-grande'
region='us-east-1'
if model_id.startswith('ai21'):
    print(ai21_model_package_json[model_id])
    print(ai21_model_package_json[model_id]['model_package_map'][region])
