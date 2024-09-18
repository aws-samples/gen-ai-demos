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
import datetime
import time
import os
import dateutil.parser
import logging
import random
import string
import boto3
import os

dynamodb = boto3.resource('dynamodb')
table_name = os.environ['TABLE_NAME']

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


# --- Helpers that build all of the responses ---


def elicit_slot(session_attributes, active_contexts, intent, slot_to_elicit, message):
  return {
    'sessionState': {
      'activeContexts':[{
        'name': 'intentContext',
        'contextAttributes': active_contexts, 
        'timeToLive': {
          'timeToLiveInSeconds': 600,
          'turnsToLive': 1
        }
      }],
      'sessionAttributes': session_attributes,
      'dialogAction': {
        'type': 'ElicitSlot',
        'slotToElicit': slot_to_elicit
      },
      'intent': intent,
    }
  }


def confirm_intent(active_contexts, session_attributes, intent, message):
  return {
    'sessionState': {
      'activeContexts': [active_contexts],
      'sessionAttributes': session_attributes,
      'dialogAction': {
        'type': 'ConfirmIntent'
      },
      'intent': intent
    }
  }


def close(session_attributes, active_contexts, fulfillment_state, intent, message):
  response = {
    'sessionState': {
      'activeContexts':[{
        'name': 'intentContext',
        'contextAttributes': active_contexts,
        'timeToLive': {
          'timeToLiveInSeconds': 600,
          'turnsToLive': 1  
        }
      }],
      'sessionAttributes': session_attributes,
      'dialogAction': {
        'type': 'Close',
      },
      'intent': intent,
    },
    'messages': [{'contentType': 'PlainText', 'content': message}]
  }
  
  return response


def delegate(session_attributes, active_contexts, intent, message):
  return {
    'sessionState': {
      'activeContexts':[{
        'name': 'intentContext',
        'contextAttributes': active_contexts,
        'timeToLive': {
          'timeToLiveInSeconds': 600,
          'turnsToLive': 1
        }
      }],
      'sessionAttributes': session_attributes,
      'dialogAction': {
        'type': 'Delegate',
      },
      'intent': intent,
    },
    'messages': [{'contentType': 'PlainText', 'content': message}]
  }


def initial_message(intent_name):
  response = {
    'sessionState': {
      'dialogAction': {
        'type': 'ElicitSlot',
        'slotToElicit': 'Location' if intent_name=='BookHotel' else 'PickUpCity'
      },
      'intent': {
        'confirmationState': 'None',
        'name': intent_name,
        'state': 'InProgress'
      }  
    }
  }
  
  return response



def book_hotel(intent_request):
  
  #access any session attributes you might wan to use.
  #session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}
  
  #Generate confirmation code, not guranteed to be unique, just for demo purposes.
  letters = random.choices(string.ascii_uppercase, k=3)
  digits = random.choices(string.digits, k=3)
  confirmation_code = ''.join(letters + digits)
        
  # Get slot values from Lex event
  inputMode = intent_request['inputMode']
  slots = intent_request['sessionState']['intent']['slots']
  comments = slots.get('ProvideComment', {}).get('value', {}).get('interpretedValue')
  
  logger.debug(comments)
  if comments == "Yes":
    logger.debug(slots.get('ProvideComment', {}).get('value', {}).get('interpretedValue'))
    # Construct DynamoDB item with comment
    item = {
      'City': slots.get('City', {}).get('value', {}).get('interpretedValue'),
      'CheckInDate': slots.get('CheckInDate', {}).get('value', {}).get('interpretedValue'),
      'NumberOfNights': slots.get('NumberOfNights', {}).get('value', {}).get('interpretedValue'),
      'NumberOfGuests': slots.get('NumberOfGuests', {}).get('value', {}).get('interpretedValue'),
      'RoomType': slots.get('RoomType', {}).get('value', {}).get('interpretedValue'),
      'ConfirmationCode': confirmation_code,
      'Comment': slots.get('Comment', {}).get('value', {}).get('interpretedValue')  
    }
  else:
    # Construct DynamoDB item without comment
    item = {
      'City': slots.get('City', {}).get('value', {}).get('interpretedValue'),
      'CheckInDate': slots.get('CheckInDate', {}).get('value', {}).get('interpretedValue'),
      'NumberOfNights': slots.get('NumberOfNights', {}).get('value', {}).get('interpretedValue'),
      'NumberOfGuests': slots.get('NumberOfGuests', {}).get('value', {}).get('interpretedValue'),
      'RoomType': slots.get('RoomType', {}).get('value', {}).get('interpretedValue'),
      'ConfirmationCode': confirmation_code
    }
    
  # Put reservation details in DynamoDB
  table = dynamodb.Table(table_name)  
  table.put_item(Item=item)
  
  
  #Update the confirmation state, state, session attributes and active contecxt of the intent.
  
  intent = intent_request['sessionState']['intent']
  
  session_attributes = {} ##TODO read and maintain existing attributes
  #session_attributes['sessionId'] = intent_request['sessionId']
  
  if 'activeContexts' in intent_request['sessionState'] and len(intent_request['sessionState']['activeContexts']):
    active_contexts = intent_request['sessionState']['activeContexts'][0]
  else:
    active_contexts = {}
  
  
  intent['confirmationState']="Confirmed"
  intent['state']="Fulfilled"
  
  if inputMode == "Text":
      return close(session_attributes, active_contexts, 'Fulfilled', intent, 'Thanks, I have placed your reservation. Your reservation number is: ' + confirmation_code) 
  else:
      return close(session_attributes, active_contexts, 'Fulfilled', intent, 'Thanks, I have placed your reservation. Your reservation number is: ' + confirmation_code[0] + ' <break time="0.3s"/> ' + confirmation_code[1] + ' <break time="0.3s"/> ' + confirmation_code[2] + ' <break time="0.3s"/> ' + confirmation_code[3] + ' <break time="0.3s"/> ' + confirmation_code[4] + ' <break time="0.3s"/> ' + confirmation_code[5])
  

# --- Intents ---


def dispatch(intent_request):
  """
  The dispatcher calls the relecant code for the intent that we are trying to fulfill.
  """
  logger.debug(intent_request)
  
  #We check which intent is used
  intent_name = intent_request['sessionState']['intent']['name']
  
  
  # Dispatch to your bot's intent handlers. Add additional intent handlers for any additional intents that are implemented
  if intent_name == 'BookHotel':
    return book_hotel(intent_request)
  
  raise Exception('Intent with name ' + intent_name + ' not supported')
    

# --- Main handler ---


def lambda_handler(event, context):
  """
  Route the incoming request based on intent. 
  The JSON body of the request is provided in the event slot.
  """
  # By default, treat the user request as coming from the America/New_York time zone.
  os.environ['TZ'] = 'America/New_York'
  time.tzset()
  logger.debug('event.bot.name={}'.format(event['bot']['name']))
  logger.debug(event)
  return dispatch(event)