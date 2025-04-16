import functions_framework
from firebase_admin import initialize_app, firestore
import firebase_admin
import json
import os
from google.cloud import storage
from google.cloud import secretmanager
import base64
from datetime import datetime
from openai import OpenAI
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin
try:
    initialize_app()
except ValueError:
    # App already initialized
    pass

# Debug: Print environment variables
print("Environment variables:")
for key, value in os.environ.items():
    if 'key' in key.lower():
        # Print masked version of sensitive values
        print(f"{key}: {'*' * 8}")
    else:
        print(f"{key}: {value}")

def access_secret_version(secret_id, version_id="latest"):
    """
    Access the secret from GCP Secret Manager
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = "pepmvp"  # Replace with your actual project ID
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        # Strip whitespace and newlines to avoid issues with API keys
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error accessing secret '{secret_id}': {str(e)}")
        raise

# Get OpenAI API key from Secret Manager
try:
    logger.info("Fetching OpenAI API key from Secret Manager...")
    openai_api_key = access_secret_version("openai-api-key")
    logger.info("Successfully retrieved OpenAI API key from Secret Manager")
except Exception as e:
    logger.error(f"Failed to retrieve OpenAI API key: {str(e)}")
    raise

# Initialize OpenAI client
try:
    logger.info("Initializing OpenAI client...")
    client = OpenAI(
        api_key=openai_api_key,
        timeout=60.0
    )
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Error initializing OpenAI client: {str(e)}")
    raise

def call_gpt4_vision(images, prompt):
    """Call GPT-4 Vision API with images and prompt."""
    
    # Convert base64 images to URLs or direct base64
    image_contents = []
    for idx, image_base64 in enumerate(images, start=1):
        image_contents.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}",
                "detail": "low", # Use low detail to reduce tokens
                "sequence": idx  # Add sequence number to each image
            }
        })
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_contents
                    ]
                }
            ],
            max_tokens=500
        )
        
        # Extract the response content
        analysis_text = response.choices[0].message.content
        
        # Parse the response into issues and suggestions
        issues = []
        suggestions = []
        current_section = None
        
        for line in analysis_text.split('\n'):
            line = line.strip()
            if 'issues' in line.lower():
                current_section = 'issues'
            elif 'suggestions' in line.lower():
                current_section = 'suggestions'
            elif line.startswith('- ') or line.startswith('* '):
                if current_section == 'issues':
                    issues.append(line[2:])
                elif current_section == 'suggestions':
                    suggestions.append(line[2:])
        
        return {
            'issues': issues,
            'suggestions': suggestions
        }
        
    except Exception as e:
        print(f"Error calling GPT-4 Vision: {str(e)}")
        raise

def store_analysis(user_id, exercise_id, analysis):
    """Store the analysis results in Firestore."""
    try:
        db = firestore.client()
        
        # Create a new analysis document
        analysis_ref = (db
            .collection('users')
            .document(user_id)
            .collection('exercises')
            .document(exercise_id)
            .collection('analyses')
            .document())
        
        # Store the analysis with timestamp
        analysis_ref.set({
            'timestamp': firestore.SERVER_TIMESTAMP,
            'issues': analysis['issues'],
            'suggestions': analysis['suggestions']
        })
        
        return True
    except Exception as e:
        print(f"Error storing analysis: {str(e)}")
        raise

@functions_framework.http
def analyze_exercise_poses(request):
    """
    HTTP Cloud Function to analyze exercise poses.
    Expects a POST request with JSON body containing:
    {
        "images": [base64_string, ...],
        "exerciseInfo": {
            "userId": string,
            "exerciseId": string,
            "name": string,
            "instructions": string
        }
    }
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

    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    
    try:
        request_json = request.get_json()
        
        if not request_json:
            return {'error': 'No JSON data provided'}, 400, headers
        
        # Validate required fields
        images = request_json.get('images', [])
        exercise_info = request_json.get('exerciseInfo', {})
        
        required_fields = ['userId', 'exerciseId', 'name', 'instructions']
        missing_fields = [field for field in required_fields if field not in exercise_info]
        
        if missing_fields:
            return {
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, 400, headers
            
        if not images:
            return {
                'error': 'At least one image is required'
            }, 400, headers
        
        # Call GPT-4 Vision API
        analysis = call_gpt4_vision(images, f"""You are a professional physical therapist.
The user is performing: {exercise_info['name']}
Instructions they should follow: {exercise_info['instructions']}

Analyze these {len(images)} sequential images of the exercise in order (1 through {len(images)}) and provide:
1. List of specific issues observed in the sequence
2. Specific suggestions for improvement

Pay special attention to the progression of the exercise through the sequence of images.
Format your response with clear sections for Issues and Suggestions, using bullet points.""")
        
        # Store the analysis
        store_analysis(
            exercise_info['userId'],
            exercise_info['exerciseId'],
            analysis
        )
        
        return {
            'success': True,
            'message': 'Analysis completed and stored successfully'
        }, 200, headers
        
    except Exception as e:
        print(f"Error in analyze_exercise_poses: {str(e)}")
        return {
            'error': 'Internal server error',
            'message': str(e)
        }, 500, headers
