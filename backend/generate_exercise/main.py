import functions_framework
import json
import uuid
import logging
import re
import requests
from google.cloud import firestore
from google.cloud import secretmanager
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firestore DB
db = db = firestore.Client(project='pepmvp', database='pep-mvp')

# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)

# Secret Manager setup
def access_secret_version(secret_id, version_id="latest"):
    """
    Access the secret from GCP Secret Manager
    """
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = "pepmvp"  # Replace with your project ID
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        # Strip whitespace and newlines to avoid issues with API keys
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error accessing secret '{secret_id}': {str(e)}")
        raise

# Predefined RSI exercises
RSI_EXERCISES = [
    {
        "name": "Wrist Rotations",
        "description": "Circular wrist movements to improve mobility and reduce stiffness",
        "target_joints": ["wrist"],
        "instructions": [
            "Make a gentle fist",
            "Rotate your wrist in full circles",
            "Do 10 reps clockwise",
            "Do 10 reps counterclockwise"
        ],
        "variations": [
            "Hold light weights (1-2 lbs)",
            "Use resistance bands for added challenge"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/wrist_rotation.mp4"
    },
    {
        "name": "Forearm Flexor/Extensor Stretch",
        "description": "Stretches to relieve tension in forearm muscles",
        "target_joints": ["wrist", "forearm"],
        "instructions": [
            "For flexor stretch:",
            "Extend your arm straight with palm up",
            "Pull fingers back with opposite hand",
            "Hold for 15-20 seconds",
            "For extensor stretch:",
            "Extend your arm straight with palm down",
            "Pull fingers toward body",
            "Hold for 15-20 seconds"
        ],
        "variations": [
            "Perform against a wall for added resistance"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/forearm_stretch.mp4"
    },
    {
        "name": "Prayer Stretch",
        "description": "A gentle stretch for wrists and forearms",
        "target_joints": ["wrist", "forearm"],
        "instructions": [
            "Press your palms together near your chest",
            "Lower your hands until your wrists separate",
            "Hold for 15-20 seconds",
            "Return to starting position and repeat"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/prayer_stretch.mp4"
    },
    {
        "name": "Finger Stretches",
        "description": "Comprehensive finger stretching exercise",
        "target_joints": ["finger", "palm"],
        "instructions": [
            "Gently pull back each finger one by one",
            "Hold each stretch for 2-3 seconds",
            "Then stretch the entire palm by pulling all fingers back simultaneously",
            "Hold for 5 seconds",
            "Return to starting position and repeat"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/finger_stretch.mp4"
    }
]

@functions_framework.http
def generate_exercise(request):
    """
    Cloud Function to generate a single recommended exercise for a user.
    
    Request format:
    {
        "user_id": "uuid-of-user",
        "llm_provider": "claude" or "openai"  (optional, defaults to openai)
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
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        request_json = request.get_json(silent=True)
        
        if not request_json or 'user_id' not in request_json:
            return (json.dumps({'error': 'Invalid request - missing user_id'}, cls=DateTimeEncoder), 400, headers)
        
        user_id = request_json['user_id']
        llm_provider = request_json.get('llm_provider', 'openai')  # Default to OpenAI
        
        logger.info(f"Processing request for user_id: {user_id}, llm_provider: {llm_provider}")
        
        # Get API keys
        if llm_provider == 'claude':
            api_key = access_secret_version("anthropic-api-key")
        else:
            api_key = access_secret_version("openai-api-key")
        
        # Get user data
        user_data = get_user_data(user_id)
        if not user_data:
            logger.warning(f"User not found: {user_id}")
            return (json.dumps({'error': 'User not found'}, cls=DateTimeEncoder), 404, headers)
        
        # Use LLM to select the most appropriate exercise and generate detailed instructions
        if llm_provider == 'claude':
            exercise = select_exercise_with_claude(user_data, api_key)
        else:
            exercise = select_exercise_with_openai(user_data, api_key)
        
        logger.info(f"Selected exercise: {exercise['name']}")
        
        # Save the exercise to Firestore
        saved_exercise = save_exercise(exercise, user_id)
        
        # Return success
        return (json.dumps({
            'status': 'success',
            'exercise': saved_exercise,
            'source': 'llm-selected'
        }, cls=DateTimeEncoder), 200, headers)
        
    except Exception as e:
        logger.error(f"Error generating exercise: {str(e)}", exc_info=True)
        return (json.dumps({'error': f'Error generating exercise: {str(e)}'}, cls=DateTimeEncoder), 500, headers)

def get_user_data(user_id):
    """
    Retrieve user data from Firestore
    """
    user_doc = db.collection('users').document(user_id).get()
    
    if not user_doc.exists:
        return None
    
    return user_doc.to_dict()

def select_exercise_with_claude(user_data, api_key):
    """
    Use Claude to select the most appropriate exercise from the predefined list
    and generate detailed instructions based on the user's pain description
    """
    try:
        # Extract user info
        name = user_data.get('name', 'the user')
        pain_description = user_data.get('pain_description', '')
        
        # Create a JSON string of all available exercises
        exercises_json = json.dumps(RSI_EXERCISES)
        
        # Construct prompt for Claude
        prompt = f"""
        I need you to select the most appropriate RSI (Repetitive Strain Injury) exercise for a user with the following profile:
        
        Name: {name}
        Pain description: {pain_description}
        
        Below is a list of predefined exercises for finger and wrist RSI. Please select the ONE most appropriate exercise based on the user's pain description:
        
        {exercises_json}
        
        After selecting the most appropriate exercise, please provide detailed instructions for that specific exercise. The instructions should be clear, step-by-step, and tailored to the user's condition.
        
        Format your response as JSON:
        {{
          "selected_exercise": {{
            "name": "Exercise Name",
            "description": "Detailed description of the exercise and its benefits for this specific user",
            "target_joints": ["finger", "wrist"],
            "instructions": [
              "Step 1: Detailed instruction",
              "Step 2: Detailed instruction",
              "Step 3: Detailed instruction",
              ...
            ],
            "variations": [
              "Variation 1: Description",
              "Variation 2: Description"
            ]
          }}
        }}
        
        Respond ONLY with the JSON object and nothing else.
        """
        
        logger.info("Calling Claude API to select exercise")
        
        # Call Claude API
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-3-opus-20240229",
                "max_tokens": 800,
                "temperature": 0.2,
                "system": "You are a senior physical therapist specializing in RSI rehabilitation for fingers and wrists.",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
        )
        
        # Parse response
        if response.status_code != 200:
            logger.error(f"Claude API error: {response.text}")
            raise Exception(f"Claude API error: {response.text}")
        
        result = response.json()
        content = result.get('content', [{}])[0].get('text', '{}')
        
        # Extract JSON from the response
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        
        if json_match:
            exercise_json = json_match.group(1)
        else:
            exercise_json = content  # Assume the content is just JSON
        
        response_data = json.loads(exercise_json)
        selected_exercise = response_data.get('selected_exercise', {})
        
        # Ensure all required fields are present
        if not all(key in selected_exercise for key in ['name', 'description', 'target_joints', 'instructions']):
            logger.warning("Missing required fields in LLM response, using fallback")
            return get_fallback_exercise()
        
        return selected_exercise
    except Exception as e:
        logger.error(f"Error in select_exercise_with_claude: {str(e)}", exc_info=True)
        # Provide a fallback exercise in case of failure
        return get_fallback_exercise()

def select_exercise_with_openai(user_data, api_key):
    """
    Use OpenAI to select the most appropriate exercise from the predefined list
    and generate detailed instructions based on the user's pain description
    """
    try:
        # Extract user info
        name = user_data.get('name', 'the user')
        pain_description = user_data.get('pain_description', '')
        
        # Create a JSON string of all available exercises
        exercises_json = json.dumps(RSI_EXERCISES)
        
        # Construct prompt for OpenAI
        prompt = f"""
        I need you to select the most appropriate RSI (Repetitive Strain Injury) exercise for a user with the following profile:
        
        Name: {name}
        Pain description: {pain_description}
        
        Below is a list of predefined exercises for finger and wrist RSI. Please select the ONE most appropriate exercise based on the user's pain description:
        
        {exercises_json}
        
        After selecting the most appropriate exercise, please provide detailed instructions for that specific exercise. The instructions should be clear, step-by-step, and tailored to the user's condition.
        
        Format your response as JSON:
        {{
          "selected_exercise": {{
            "name": "Exercise Name",
            "description": "Detailed description of the exercise and its benefits for this specific user",
            "target_joints": ["finger", "wrist"],
            "instructions": [
              "Step 1: Detailed instruction",
              "Step 2: Detailed instruction",
              "Step 3: Detailed instruction",
              ...
            ],
            "variations": [
              "Variation 1: Description",
              "Variation 2: Description"
            ]
          }}
        }}
        
        Respond ONLY with the JSON object and nothing else.
        """
        
        logger.info("Calling OpenAI API to select exercise")
        
        # Call OpenAI API
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "You are a senior physical therapist specializing in RSI rehabilitation for fingers and wrists."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 800
            }
        )
        
        # Parse response
        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.text}")
            raise Exception(f"OpenAI API error: {response.text}")
        
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        
        response_data = json.loads(content)
        selected_exercise = response_data.get('selected_exercise', {})
        
        # Ensure all required fields are present
        if not all(key in selected_exercise for key in ['name', 'description', 'target_joints', 'instructions']):
            logger.warning("Missing required fields in LLM response, using fallback")
            return get_fallback_exercise()
        
        return selected_exercise
    except Exception as e:
        logger.error(f"Error in select_exercise_with_openai: {str(e)}", exc_info=True)
        # Provide a fallback exercise in case of failure
        return get_fallback_exercise()

def save_exercise(exercise, user_id):
    """
    Save the exercise to Firestore
    """
    exercise_id = str(uuid.uuid4())
    created_at = datetime.now()
    
    exercise_doc = {
        'id': exercise_id,
        'user_id': user_id,
        'name': exercise['name'],
        'description': exercise['description'],
        'target_joints': exercise['target_joints'],
        'instructions': exercise['instructions'],
        'variations': exercise.get('variations', []),
        'videoURL': exercise.get('videoURL'),
        'created_at': created_at,
        'updated_at': created_at
    }
    
    # Save to Firestore
    db.collection('exercises').document(exercise_id).set(exercise_doc)
    logger.info(f"Saved exercise with ID: {exercise_id}")
    
    return exercise_doc

def get_fallback_exercise():
    """
    Return a fallback exercise when API calls fail
    """
    return {
        "name": "Wrist Rotations",
        "description": "Circular wrist movements to improve mobility and reduce stiffness. This exercise helps to maintain range of motion in the wrist joint and can help alleviate symptoms of RSI.",
        "target_joints": ["wrist"],
        "instructions": [
            "Make a gentle fist with your hand",
            "Slowly rotate your wrist in full circles, 10 times clockwise",
            "Then rotate 10 times counterclockwise",
            "Keep your forearm stable and only move your wrist",
            "Perform this exercise 2-3 times per day"
        ],
        "variations": [
            "Hold light weights (1-2 lbs) for added resistance",
            "Use resistance bands for a more challenging workout"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/wrist_rotation.mp4"
    }