import os
import re
import functions_framework
import json
import uuid
import logging
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
    Cloud Function to handle patient onboarding with minimal data.
    
    Required fields:
    - name (str): Patient's name
    - injury (str): Description of the injury or pain
    - pain_level (int): Pain level on a scale of 1-10
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
        name = request_json.get('name')
        injury = request_json.get('injury')
        pain_level = request_json.get('pain_level')
        # Check for missing required fields
        if not name or not injury:
            error_msg = "Missing required fields: name, injury, and pain_level are required"
            logger.error(error_msg)
            return (json.dumps({'error': error_msg}), 400, headers)
        
        # Create patient ID
        patient_id = str(uuid.uuid4())
        created_at = datetime.now()

        # Create and store patient document with minimal data
        patient_doc = {
            'id': patient_id,
            'name': name,
            'injury': injury,
            'pain_level': pain_level,
            'created_at': created_at,
            'updated_at': created_at
        }

        # Save to Firestore
        db.collection('patients').document(patient_id).set(patient_doc)
        logger.info(f"Created patient with ID: {patient_id}")

        # Return success response
        return (json.dumps({
            'status': 'success',
            'message': 'Patient onboarded successfully',
            'patient_id': patient_id
        }), 200, headers)
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return (json.dumps({'error': f'Error processing request: {str(e)}'}), 500, headers)