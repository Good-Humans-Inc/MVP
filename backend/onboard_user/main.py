import os
import re
import functions_framework
import json
import uuid
import logging
import requests
from google.cloud import firestore
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firestore DB
db = db = firestore.Client(project='pepmvp', database='pep-mvp')

@functions_framework.http
def onboard_user(request):
    """
    Cloud Function to handle user onboarding with minimal data.
    
    Required fields:
    - user_name (str): User's name
    - pain_description (str): Description of the pain
    Optional fields:
    - pain_level (int): Pain level on a scale of 1-10 (optional)
    - notification_time (str): Preferred time for daily notifications (format: "HH:MM")
    """
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        request_json = request.get_json(silent=True)
        
        if not request_json:
            logger.error("Invalid request - missing JSON data")
            return (json.dumps({'error': 'Invalid request - missing data'}), 400, headers)
        
        # Log incoming request for debugging
        logger.info(f"Received request: {json.dumps(request_json)}")
        
        # Extract fields
        user_name = request_json.get('user_name')
        pain_description = request_json.get('pain_description')

        pain_level = request_json.get('pain_level') # Extract pain_level (will be None if not provided)
        notification_time = request_json.get('notification_time')
        # Check for missing required fields
        if not user_name or not pain_description:
            error_msg = "Missing required fields: user_name and pain_description are required"
            logger.error(error_msg)
            return (json.dumps({'error': error_msg}), 400, headers)
        
        # Create user ID
        user_id = str(uuid.uuid4())
        created_at = datetime.now()

        # Create and store user document with minimal data
        user_doc = {
            'id': user_id,
            'user_name': user_name,
            'pain_description': pain_description,
            'created_at': created_at,
            'updated_at': created_at
        }

        # Add optional fields if they exist
        if pain_level is not None:
            user_doc['pain_level'] = pain_level
        
        # Save to Firestore
        db.collection('users').document(user_id).set(user_doc)
        logger.info(f"Created user with ID: {user_id}")

        # --- Call update_information to set initial notification preferences (if provided) ---
        if notification_time:
            try:
                # Construct URL (replace with your actual region and project if different)
                update_info_url = f"https://us-central1-pepmvp.cloudfunctions.net/update_information"
                
                # Prepare payload (only send notification_time and user_id)
                # update_information will handle timezone extraction/defaulting
                payload = {
                    'user_id': user_id,
                    'notification_time': notification_time 
                }
                
                logger.info(f"Calling update_information for user {user_id} with notification time {notification_time}")
                
                response = requests.post(update_info_url, json=payload, timeout=15) # Added timeout
                response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                
                logger.info(f"Successfully called update_information. Status: {response.status_code}")

            except requests.exceptions.RequestException as req_err:
                # Log errors from the update_information call but don't fail the onboarding
                logger.error(f"Error calling update_information for user {user_id}: {str(req_err)}")
                # Optionally, you could add more specific error handling here
                # For the demo, we log the error and proceed.
            except Exception as update_err:
                 # Catch any other unexpected errors during the update call
                 logger.error(f"Unexpected error calling update_information for user {user_id}: {str(update_err)}")
        else:
            logger.info(f"No notification_time provided for user {user_id}. Skipping call to update_information.")
        # --- End call to update_information ---

        # Return success response for onboarding
        return (json.dumps({
            'status': 'success',
            'message': 'User onboarded successfully',
            'user_id': user_id
        }), 200, headers)
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return (json.dumps({'error': f'Error processing request: {str(e)}'}), 500, headers)