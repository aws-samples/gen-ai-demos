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

"""
This sample demonstrates an implementation of the Lex Code Hook Interface
in order to serve a sample bot which manages reservations for hotel rooms and car rentals.
Bot, Intent, and Slot models which are compatible with this sample can be found in the Lex Console
as part of the 'BookTrip' template.
This sample is compatible with the Amazon Lex V2 data structure. It can be invoked as a Lambda Hook
at the Fulfillment section of both intents included in the bot configuration (BookHotel and BookCar),
as well as an initialization and validation function at each turn of the dialog.   
For instructions on how to set up and test this bot, as well as additional samples,
visit the Lex Getting Started documentation http://docs.aws.amazon.com/lex/latest/dg/getting-started.html.
"""
import json
import boto3
import os
import datetime

# name of the DynamoDB table to store policies - this should come from Lambda environment variable
#tablename = 'insurance-ddb'
tablename = os.environ["HOTEL_RESERVATION_TABLE"]
kbid = os.environ["KNOWLEDGEBASE_ID"]
query_slot = os.environ["query_slot"]
model = os.environ["model_id"]
#case_query_slot = os.environ["case_query_slot"]
#case_query_RAG_slot = os.environ["case_query_RAG_slot"]
#case_kbid = os.environ["case_kb_ID"]
print("table name is: " + tablename)
dynamodb = boto3.client('dynamodb')
ssm = boto3.client('ssm')
bedrock_kb = boto3.client('bedrock-agent-runtime')
bedrock_runtime = boto3.client('bedrock-runtime')
agent_call_list = ["agent", "customer service rep","customer service representative", "csr", "customer service", "representative", "rep", "human"]
session = boto3.Session()
region = session.region_name

# Seed a SSM parameter for policy Number only the first time
try:
    test = ssm.get_parameter(Name="latest_hotel_nr", WithDecryption=True)
except ssm.exceptions.ParameterNotFound:
    print("seeding the reservation confirmation number parameter")
    ssm.put_parameter(Name="latest_hotel_nr", Value="2001001", Type="String", Overwrite=True)

fulfillment_state = 'Fulfilled'

def invoke_bedrock(query, knowledgebase_response, prevResponse):
    prev_prompt = "Use this previous response as context when answering this current question if the current question is related to this context: " + prevResponse
    query_prompt = "Answer this question: " + query + " from this retrieved text: " + knowledgebase_response + ". " + prev_prompt
    model_id = model
    body = json.dumps({
            "prompt": f"\n\nHuman: {query_prompt}\n\nAssistant:",
            "max_tokens_to_sample": 2056,
            "temperature": 0.0,
            "top_k": 250,
            "top_p": 0.1,
            "stop_sequences": ["\n\nHuman:"],
            "anthropic_version": "bedrock-2023-05-31"
        })
    bedrock_response = bedrock_runtime.invoke_model(
            body=body,
            modelId=model_id,
            accept="*/*",
            contentType="application/json"
        )

    response_body = json.loads(bedrock_response.get("body").read())
    print("response body in invoke bedrock is: " + str(response_body))
    return str(response_body.get("completion"))

def get_slots(intent_request):
    return intent_request['sessionState']['intent']['slots']

def get_slot(intent_request, slotName):
    slots = get_slots(intent_request)
    if slots is not None and slotName in slots and slots[slotName] is not None:
        return slots[slotName]['value']['interpretedValue']
    else:
        return None

def get_session_attributes(intent_request):
    sessionState = intent_request['sessionState']
    if 'sessionAttributes' in sessionState:
        return sessionState['sessionAttributes']

    return {}

def elicit_slot(slotToElicit, intent_request, session_attributes, message):
    intent_request['sessionState']['intent']['state'] = 'InProgress'
    return {
        'sessionState': {
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': slotToElicit
            },
            'intent': intent_request['sessionState']['intent']
        },
        'requestAttributes': intent_request['requestAttributes'] if 'requestAttributes' in intent_request else None,
        'messages': [ message ] if message != None else None
    }

def elicit_intent(intent_request, session_attributes, message):
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitIntent'
            },
            'sessionAttributes': session_attributes
        },
        'messages': [ message ] if message != None else None,
        'requestAttributes': intent_request['requestAttributes'] if 'requestAttributes' in intent_request else None
    }


def close(intent_request, session_attributes, fulfillment_state, message):
    intent_request['sessionState']['intent']['state'] = fulfillment_state
    return {
        'sessionState': {
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'Close'
            },
            'intent': intent_request['sessionState']['intent']
        },
        'messages': [message],
        'sessionId': intent_request['sessionId'],
        'requestAttributes': intent_request['requestAttributes'] if 'requestAttributes' in intent_request else None
    }

def GetQnA_gen(intent_request):
    session_attributes = get_session_attributes(intent_request)
    slots = get_slots(intent_request)
    #confirmationSlot = get_slot(intent_request, 'sl_confirmationSlot')
    # Let us get our slot values
    query = get_slot(intent_request,case_query_slot)
    print('Input query to Case KB is: ' + str(query))
    response = bedrock_kb.retrieve(
        knowledgeBaseId = case_kbid,
        retrievalQuery={
            'text':query
        },
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults':3
            }
        }
    )
    print("Case KB response is: " + str(response))
    #case_kb_response = str(response['retrievalResults'][0]['content']['text'])
    #case_kb_source = str(response['retrievalResults'][0]['location']['s3Location']['uri'])

    case_kb_response = ""
    case_kb_source = ""
    for kbres in response['retrievalResults']:
        case_kb_response += str(kbres['content']['text']) + "\n\n"
        case_kb_source += str(kbres['location']['s3Location']['uri']) + "\n\n"

    generated_response = invoke_bedrock(query, case_kb_response)

    session_attributes['prevResponse'] = generated_response

    full_response = str(generated_response+'. Source attribution:::\n\n'+case_kb_source)

    message =  {
            'contentType': 'PlainText',
            'content': full_response
        }
    return elicit_slot(case_query_slot, intent_request, session_attributes, message)

def GetQnA(intent_request):
    session_attributes = get_session_attributes(intent_request)
    prevResponse = " "
    if 'prevResponse' in session_attributes:
        prevResponse = session_attributes['prevResponse']
    slots = get_slots(intent_request)
    # Let us get our slot values
    query = get_slot(intent_request,query_slot)
    print('Input query to KB is: ' + str(query))
    
    
    session_attributes['prevResponses'] = query
    # Agent transfer using sentiments
    #sent_query = "Detect the emotion of this user response and return only one of Green, Amber or Red. Green means the user is pleased with the interaction so far and is not agitated. Amber means the user is starting to get frustrated. Red means the user is very angry and agitated: " + query
    #sentiment = invoke_bedrock(sent_query)
    #print("Emotion response from BEDROCK is: " + str(sentiment))
    '''
    if "red" in sentiment.lower():
        print("User emotion is RED. Transfering to a live agent")
        full_response = "I am sorry to hear that."
        message =  {
                    'contentType': 'PlainText',
                    'content': full_response
                }
        session_attributes['agent_requested'] = "yes"
        return close(intent_request, session_attributes, fulfillment_state, message)
    '''
    if any(word in query for word in agent_call_list):
        full_response = "Sure thing."
        message =  {
                    'contentType': 'PlainText',
                    'content': full_response
                }
        session_attributes['agent_requested'] = "yes"
        return close(intent_request, session_attributes, fulfillment_state, message)
    else:
        model_arn = 'arn:aws:bedrock:'+region+'::foundation-model/'+model
        response = bedrock_kb.retrieve_and_generate(
            input={
                'text':query
            },
            retrieveAndGenerateConfiguration={
                'type':'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration':{
                    'knowledgeBaseId':kbid,
                    'modelArn': model_arn
                }
            },
        )
        print("KB response is: " + str(response))
        kb_response = str(response['output']['text'])
        if len(response['citations'][0]['retrievedReferences']) > 0:
            kb_source = "\n\n Source Attribution::: \n\n" + str(response['citations'][0]['retrievedReferences'][0]['location']['s3Location']['uri'])
        else:
            kb_source = " "
        
        session_attributes['prevResponse'] = kb_response

        full_response = str(kb_response) + ". Is there anything else I can help you with?" #+ kb_source) 

        # End

        message =  {
                'contentType': 'PlainText',
                'content': full_response
            }
        return elicit_slot(query_slot, intent_request, session_attributes, message)    



def GetReservationStatus(intent_request):
    session_attributes = get_session_attributes(intent_request)
    slots = get_slots(intent_request)

    #confirmationSlot = get_slot(intent_request, 'sl_confirmationSlot')
    # Let us get our slot values
    res_nr = get_slot(intent_request,'ReservationNumber')
    print('Reservation Number is: ' + str(res_nr))
    # Get order status from dynamodb
    response = dynamodb.get_item(
    TableName=tablename,
    Key={
        'ReservationNr': {
            'S': str(res_nr)
                }
            }
        )

    print("DDB response is: " + str(response))
    if response.get('Item'):
        city = response['Item']['City']['S']
        check_in_date = response['Item']['CheckInDate']['S']
        num_nights = response['Item']['NumberOfNights']['N']
        num_guests = response['Item']['NumberOfGuests']['N']
        room_type = response['Item']['RoomType']['S']
        city = response['Item']['City']['S']
        res_nr = response['Item']['ReservationNr']['S']
        #first_name = response['Item']['FirstName']['S']
        #last_name = response['Item']['LastName']['S']
        res_status = response['Item']['ResStatus']['S']
        if res_status in "Canceled":
            text = "I am sorry I did not recognize that reservation confirmation number or it might have been canceled. Can you please provide me a valid reservation confirmation number?"
        else:
            text = f"Thank you {first_name} {last_name}, I found your reservation. You have travel booked for {num_nights} number of nights with {num_guests} guests in city {city} for date {check_in_date}. Is there anything else I can help you with today?"
    else:
        text = "I am sorry I did not recognize that reservation confirmation number. Can you please provide me a valid reservation confirmation number?"
    
    message =  {
            'contentType': 'PlainText',
            'content': text
        }
    if any(word in slots for word in agent_call_list):
        full_response = "Sure thing."
        message =  {
                    'contentType': 'PlainText',
                    'content': full_response
                }
        session_attributes['agent_requested'] = "yes"
        return close(intent_request, session_attributes, fulfillment_state, message)
    
    return close(intent_request, session_attributes, fulfillment_state, message)

def CreateReservation(intent_request):
    session_attributes = get_session_attributes(intent_request)
    slots = get_slots(intent_request)
    print('Intent request values are: ' + str(intent_request))
    
    city = get_slot(intent_request,'City')
    check_in_date = get_slot(intent_request,'CheckInDate')
    num_nights = get_slot(intent_request,'NumberOfNights')
    num_guests = get_slot(intent_request,'NumberOfGuests')
    room_type = get_slot(intent_request,'RoomType')
    #first_name = get_slot(intent_request,'FirstName')
    #last_name = get_slot(intent_request,'LastName')
    res_status = "Confirmed"

    res_date = str(datetime.date.today())

    # First determine the max value for our policy number primary key from parameter store
    ParamName = 'latest_hotel_nr'
    ssm_res = ssm.get_parameter(Name=ParamName, WithDecryption=True)
    res_nr = int(ssm_res['Parameter']['Value'])+1

    item={
            'ReservationNr': {'S': str(res_nr)},
            #'FirstName': {'S': str(first_name)},
            #'LastName': {'S': str(last_name)},
            'ResStatus': {'S': str(res_status)},
            'ResDate': {'S': str(res_date)},
            'City': {'S': str(city)},
            'RoomType': {'S': str(room_type)},
            'CheckInDate': {'S': str(check_in_date)},
            'NumberOfNights': {'N': str(num_nights)},
            'NumberOfGuests': {'N': str(num_guests)},
            }
            
    print('Saving item: ' + str(item))
    # Create the order in DynamoDB table
    dynamodb.put_item(
           TableName=tablename,
           Item={
            'ReservationNr': {'S': str(res_nr)},
            #'FirstName': {'S': str(first_name)},
            #'LastName': {'S': str(last_name)},
            'ResStatus': {'S': str(res_status)},
            'ResDate': {'S': str(res_date)},
            'City': {'S': str(city)},
            'RoomType': {'S': str(room_type)},
            'CheckInDate': {'S': str(check_in_date)},
            'NumberOfNights': {'N': str(num_nights)},
            'NumberOfGuests': {'N': str(num_guests)},
            }
        )

    # Now update SSM parameter store with the new policy Number
    ssm.put_parameter(Name=ParamName, Value=str(res_nr), Type="String", Overwrite=True)

    text = f"Thank you, your reservation is confirmed: {res_nr}. We look forward to welcoming you aboard. Is there anything else I can help you with today?"
    message =  {
            'contentType': 'PlainText',
            'content': text
        }
    if any(word in slots for word in agent_call_list):
        full_response = "Sure thing."
        message =  {
                    'contentType': 'PlainText',
                    'content': full_response
                }
        session_attributes['agent_requested'] = "yes"
        return close(intent_request, session_attributes, fulfillment_state, message)
    
    return close(intent_request, session_attributes, fulfillment_state, message)
"""
def ModifyReservation(intent_request):
    session_attributes = get_session_attributes(intent_request)
    slots = get_slots(intent_request)
    print('Slot values are: ' + str(slots))
    res_nr = get_slot(intent_request,'ReservationNumber')
    last_name = get_slot(intent_request, 'LastName')
    print('Reservations number in modify reservations is: ' + str(res_nr))
    print('Last Name in modify reservations is: ' + str(last_name))
    # Get order status from dynamodb
    response = dynamodb.get_item(
    TableName=tablename,
    Key={
        'ReservationNr': {
            'S': str(res_nr)
                }
            }
        )

    if response.get('Item'):
        first_name = response['Item']['FirstName']['S']
        last_name = response['Item']['LastName']['S']
        city = response['Item']['City']['S']
        res_status = response['Item']['ResStatus']['S']
        res_date = response['Item']['ResDate']['S']
        checkInDate = response['Item']['CheckInDate']['S']
        numberOfNights = response['Item']['NumberOfNights']['N']
        numberOfGuests = response['Item']['NumberOfGuests']['N']
        room_type = response['Item']['RoomType']['S']

        
        modified_city = get_slot(intent_request,'City')
        modified_check_in_date = get_slot(intent_request,'CheckInDate')
        modified_num_nights = get_slot(intent_request,'NumberOfNights')
        modified_num_guests = get_slot(intent_request,'NumberOfGuests')
        modified_room_type = get_slot(intent_request,'RoomType')
        modified_first_name = get_slot(intent_request,'FirstName')
        modified_last_name = get_slot(intent_request,'LastName')
        modified_res_status = "Modified"
        modified_date = str(datetime.date.today())
        

        # Update the order in DynamoDB table
        dynamodb.put_item(
           TableName=tablename,
           Item={
            'ReservationNr': {'S': str(res_nr)},
            'FirstName': {'S': str(modified_first_name)},
            'LastName': {'S': str(modified_last_name)},
            'ResStatus': {'S': str(modified_res_status)},
            'ResDate': {'S': str(modified_date)},
            'City': {'S': str(modified_city)},
            'RoomType': {'S': str(modified_room_type)},
            'CheckInDate': {'S': str(modified_check_in_date)},
            'NumberOfNights': {'N': (modified_num_nights)},
            'NumberOfGuests': {'N': (modified_num_guests)},
            }
        )


        text = f"Thank you, your reservation has been modified as requested for departure from {modified_start_city} on {modified_departure_date} and returning on {modified_city} from {modified_end_city} for {modified_seat_qty} passengers. Your confirmation number is {res_nr}. Is there anything else I can help you with?"
        message =  {
                'contentType': 'PlainText',
                'content': text
            }
        
        if any(word in slots for word in agent_call_list):
            full_response = "Sure thing."
            message =  {
                        'contentType': 'PlainText',
                        'content': full_response
                    }
            session_attributes['agent_requested'] = "yes"
            return close(intent_request, session_attributes, fulfillment_state, message)
        return close(intent_request, session_attributes, fulfillment_state, message)
    else:
        text = "I am sorry I could not locate that reservation confirmation number. Can you please check and try again?"
        message =  {
                'contentType': 'PlainText',
                'content': text
            }
        return elicit_intent(intent_request, session_attributes, message)
"""


def CancelReservation(intent_request):
    session_attributes = get_session_attributes(intent_request)
    slots = get_slots(intent_request)
    print('Slot values are: ' + str(slots))
    res_nr = get_slot(intent_request,'ReservationNumber')
    cancellation_reason = get_slot(intent_request, 'CancellationReason')
    print('Res Number is: ' + str(res_nr))
    # Get order status from dynamodb
    response = dynamodb.get_item(
    TableName=tablename,
    Key={
        'ReservationNr': {
            'S': str(res_nr)
                }
            }
        )

    if response.get('Item'):
        modified_res_status = "Canceled"
        payment_status = "Booking fee will be refunded to the original form of payment by: " + str(datetime.date.today() + datetime.timedelta(days=10))
        city = response['Item']['City']['S']
        
        # Update the res in DynamoDB table
        dynamodb.put_item(
           TableName=tablename,
           Item={
            'ReservationNr': {'S': str(res_nr)},
            'ResStatus': {'S': str(modified_res_status)},
            'City': {'S': str(city)},
            }
        )


        text = f"Thank you, your reservation has been canceled as requested. Your payment status is: {payment_status}. Is there anything else I can help you with?"
        
        message =  {
                'contentType': 'PlainText',
                'content': text
            }
        if any(word in slots for word in agent_call_list):
            full_response = "Sure thing."
            message =  {
                        'contentType': 'PlainText',
                        'content': full_response
                    }
            session_attributes['agent_requested'] = "yes"
            return close(intent_request, session_attributes, fulfillment_state, message)
        return close(intent_request, session_attributes, fulfillment_state, message)
    else:
        text = "I am sorry I could not locate that reservation confirmation number. Can you please check and try again?"
        message =  {
                'contentType': 'PlainText',
                'content': text
            }
        return elicit_intent(intent_request, session_attributes, message)

def FallbackIntent(intent_request):
    session_attributes = get_session_attributes(intent_request)
    slots = get_slots(intent_request)

    text = "I am sorry I did not understand your request. You can say things like - I need information, get order status, create order or cancel order"
    message =  {
            'contentType': 'PlainText',
            'content': text
        }
    return elicit_intent(intent_request, session_attributes, message)

def dispatch(intent_request):
    intent_name = intent_request['sessionState']['intent']['name']
    response = None
    # Dispatch to your bot's intent handlers
    if intent_name == 'BookHotel':
        print("Going with hotel booking")
        return CreateReservation(intent_request)
    #elif intent_name == 'ModifyReservation':
    #    return ModifyReservation(intent_request)
    elif intent_name == 'CancelReservation':
        return CancelReservation(intent_request)
    elif intent_name == 'QnA':
        return GetQnA(intent_request)
    elif intent_name == 'FallbackIntent':
        return FallbackIntent(intent_request)
    
    return GetQnA(intent_request)
    #raise Exception('Intent with name ' + intent_name + ' not supported')

def lambda_handler(event, context):
    print(event)
    response = dispatch(event)
    return response
