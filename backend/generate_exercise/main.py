import functions_framework
import json
import uuid
import logging
import re
import requests
from google.cloud import firestore
from google.cloud import secretmanager
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

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

# Shoulder exercises
SHOULDER_EXERCISES = [
    {
        "name": "Shoulder Rolls",
        "description": "Gentle circular movements of the shoulders to improve mobility and reduce tension",
        "target_joints": ["shoulder"],
        "instructions": [
            "Stand or sit with your back straight",
            "Roll your shoulders forward in a circular motion",
            "Repeat 5 times",
            "Roll your shoulders backward in a circular motion",
            "Repeat 5 times"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/shoulder_rolls.mp4"
    },
    {
        "name": "Wall Slides",
        "description": "Sliding arms up and down against a wall to improve shoulder mobility and posture",
        "target_joints": ["shoulder"],
        "instructions": [
            "Stand with your back against a wall",
            "Keep elbows bent at 90 degrees, touching the wall",
            "Slide your arms up the wall while maintaining contact",
            "Lower back down slowly",
            "Repeat 10 times"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/wall_slides.mp4"
    },
    {
        "name": "Cross-Body Shoulder Stretch",
        "description": "Gentle stretch for the posterior shoulder",
        "target_joints": ["shoulder"],
        "instructions": [
            "Bring one arm across your chest",
            "Use other arm to apply gentle pressure above the elbow",
            "Hold for 30 seconds",
            "Release and repeat on other side",
            "Do 3 sets per side"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/cross_body_shoulder_stretch.mp4"
    }
]

# Knee exercises
KNEE_EXERCISES = [
    {
        "name": "Straight Leg Raises",
        "description": "Strengthening exercise for the quadriceps while keeping knee straight",
        "target_joints": ["knee"],
        "instructions": [
            "Lie on your back with one leg straight and other bent",
            "Tighten thigh muscles of straight leg",
            "Lift straight leg about 6 inches off ground",
            "Hold for 5 seconds",
            "Lower slowly and repeat 10 times"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/straight_leg_raises.mp4"
    },
    {
        "name": "Wall Squats",
        "description": "Controlled squat exercise using wall support",
        "target_joints": ["knee"],
        "instructions": [
            "Stand with back against wall",
            "Slide down wall until thighs are parallel to ground",
            "Hold position for 5-10 seconds",
            "Slide back up",
            "Repeat 10 times"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/wall_squats.mp4"
    },
    {
        "name": "Knee Flexion and Extension",
        "description": "Range of motion exercise for the knee joint",
        "target_joints": ["knee"],
        "instructions": [
            "Sit in a chair with feet flat on ground",
            "Slowly straighten one knee",
            "Hold for 5 seconds",
            "Slowly bend knee back to starting position",
            "Repeat 10 times per leg"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/knee_flexion_extension.mp4"
    }
]

# Lower back exercises
LOWER_BACK_EXERCISES = [
    {
        "name": "Bridge Exercise",
        "description": "Strengthening exercise for lower back and glutes",
        "target_joints": ["lower_back"],
        "instructions": [
            "Lie on back with knees bent",
            "Lift hips toward ceiling",
            "Hold for 5 seconds",
            "Lower slowly",
            "Repeat 10 times"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/bridge_exercise.mp4"
    },
    {
        "name": "Bird Dog",
        "description": "Balance and stability exercise for core and back",
        "target_joints": ["lower_back"],
        "instructions": [
            "Start on hands and knees",
            "Extend right arm and left leg",
            "Hold for 5 seconds",
            "Return to start and switch sides",
            "Repeat 10 times per side"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/bird_dog.mp4"
    },
    {
        "name": "Knee to Chest Stretch",
        "description": "Gentle stretch for lower back muscles",
        "target_joints": ["lower_back"],
        "instructions": [
            "Lie on back with knees bent",
            "Bring one knee toward chest",
            "Hold for 30 seconds",
            "Lower and switch legs",
            "Repeat 3 times per leg"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/knee_to_chest_stretch.mp4"
    }
]

# Ankle exercises
ANKLE_EXERCISES = [
    {
        "name": "Ankle Circles",
        "description": "Range of motion exercise for ankle mobility",
        "target_joints": ["ankle"],
        "instructions": [
            "Sit with leg extended",
            "Rotate ankle clockwise 10 times",
            "Rotate ankle counterclockwise 10 times",
            "Repeat with other ankle",
            "Do 3 sets per ankle"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/ankle_circles.mp4"
    },
    {
        "name": "Ankle Alphabet",
        "description": "Mobility exercise writing alphabet with toes",
        "target_joints": ["ankle"],
        "instructions": [
            "Sit with leg extended",
            "Use your toes to write alphabet in air",
            "Move only your ankle, not your leg",
            "Go slowly and deliberately",
            "Repeat with other ankle"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/ankle_alphabet.mp4"
    },
    {
        "name": "Heel-Toe Raises",
        "description": "Strengthening exercise for ankle stability",
        "target_joints": ["ankle"],
        "instructions": [
            "Stand holding onto chair for balance",
            "Rise onto toes, then onto heels",
            "Alternate between positions",
            "Move slowly and controlled",
            "Repeat 15 times"
        ],
        "videoURL": "https://storage.googleapis.com/mvp-vids/heel_toe_raises.mp4"
    }
]

# Combine all exercises
ALL_EXERCISES = RSI_EXERCISES + SHOULDER_EXERCISES + KNEE_EXERCISES + LOWER_BACK_EXERCISES + ANKLE_EXERCISES

@functions_framework.http
def generate_exercise(request):
    """
    Cloud Function to generate a single recommended exercise for a user.
    
    Request format:
    {
        "user_id": "uuid-of-user",
        "llm_provider": "claude" or "openai"  (optional, defaults to openai)
        "target_joint": "wrist", "shoulder", "knee", etc. (optional)
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
        target_joint = request_json.get('target_joint')  # Optional target joint
        
        logger.info(f"Processing request for user_id: {user_id}, llm_provider: {llm_provider}, target_joint: {target_joint}")
        
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
        
        # Determine target joint from injury if not explicitly provided
        if not target_joint and 'injury' in user_data:
            injury = user_data['injury'].lower()
            print(f"📋 Checking injury description: '{injury}'")
            
            # Define injury keywords for each joint type
            joint_keywords = {
                'wrist': ['wrist', 'carpal'],
                'finger': ['finger', 'hand'],
                'shoulder': ['shoulder', 'arm', 'upper back'],
                'knee': ['knee', 'leg'],
                'lower_back': ['back', 'spine', 'lumbar', 'posture'],
                'ankle': ['ankle', 'foot', 'feet']
            }
            
            # Check if injury description contains any joint keywords
            for joint, keywords in joint_keywords.items():
                if any(keyword in injury for keyword in keywords):
                    target_joint = joint
                    print(f"📋 Detected target joint from injury: {target_joint}")
                    break
        
        # Filter exercises by target joint if specified
        exercises_to_consider = ALL_EXERCISES
        if target_joint:
            # Special case for finger - use finger or wrist exercises
            if target_joint == 'finger':
                finger_exercises = [ex for ex in ALL_EXERCISES if 'finger' in ' '.join(ex.get('target_joints', [])).lower()]
                wrist_exercises = [ex for ex in ALL_EXERCISES if 'wrist' in ex.get('target_joints', [])]
                exercises_to_consider = finger_exercises + wrist_exercises
                print(f"📋 Selected {len(exercises_to_consider)} exercises for finger/wrist")
            else:
                exercises_to_consider = [ex for ex in ALL_EXERCISES if target_joint in ex.get('target_joints', [])]
            
            if not exercises_to_consider:
                logger.warning(f"No exercises found for target joint: {target_joint}")
                return (json.dumps({'error': f'No exercises found for target joint: {target_joint}'}, cls=DateTimeEncoder), 404, headers)
        
        # Use LLM to select the most appropriate exercise and generate detailed instructions
        if llm_provider == 'claude':
            exercise = select_exercise_with_claude(user_data, api_key, exercises_to_consider)
        else:
            exercise = select_exercise_with_openai(user_data, api_key, exercises_to_consider)
        
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
        print("❌ get_user_data: User not found in Firestore")
        return None

    user_data = user_doc.to_dict()
    print("📋 User data retrieved from Firestore:", user_data)
    print("📋 injury field:", user_data.get('injury'))
    print("📋 pain_description field:", user_data.get('pain_description'))
    
    return user_data

def select_exercise_with_claude(user_data, api_key, exercises=None):
    """
    Use Claude to select the most appropriate exercise from the predefined list
    and generate detailed instructions based on the user's pain description
    """
    try:
        # Extract user info
        name = user_data.get('name', 'the user')
        # Use the injury field instead of pain_description
        pain_description = user_data.get('injury', '')
        print(f"📋 Using pain description for Claude: '{pain_description}'")
        
        # Use specified exercises or default to all RSI exercises
        exercises_to_use = exercises if exercises is not None else RSI_EXERCISES
        
        # If user has finger pain, prioritize finger exercises
        if pain_description and 'finger' in pain_description.lower():
            finger_exercises = [ex for ex in ALL_EXERCISES if 'finger' in ' '.join(ex.get('target_joints', [])).lower()]
            if finger_exercises:
                print(f"📋 Found {len(finger_exercises)} finger exercises based on injury")
                exercises_to_use = finger_exercises
        
        # Create a JSON string of all available exercises
        exercises_json = json.dumps(exercises_to_use)
        
        # Construct prompt for Claude
        prompt = f"""
        I need you to select the most appropriate exercise for a user with the following profile:
        
        Name: {name}
        Pain description: {pain_description}
        
        Below is a list of predefined exercises. Please select the ONE most appropriate exercise based on the user's pain description:
        
        {exercises_json}
        
        After selecting the most appropriate exercise, please provide detailed instructions for that specific exercise. The instructions should be clear, step-by-step, and tailored to the user's condition.
        
        Format your response as JSON:
        {{
          "selected_exercise": {{
            "name": "Exercise Name",
            "description": "Detailed description of the exercise and its benefits for this specific user",
            "target_joints": ["joint1", "joint2"],
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
                "system": "You are a senior physical therapist specializing in rehabilitation.",
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
            return get_fallback_exercise(exercises_to_use)
        
        # Preserve videoURL from original exercise if available
        for exercise in exercises_to_use:
            if exercise['name'] == selected_exercise['name'] and 'videoURL' in exercise:
                selected_exercise['videoURL'] = exercise['videoURL']
                break
        
        return selected_exercise
    except Exception as e:
        logger.error(f"Error in select_exercise_with_claude: {str(e)}", exc_info=True)
        # Provide a fallback exercise in case of failure
        return get_fallback_exercise(exercises)

def select_exercise_with_openai(user_data, api_key, exercises=None):
    """
    Use OpenAI to select the most appropriate exercise from the predefined list
    and generate detailed instructions based on the user's pain description
    """
    try:
        # Extract user info
        name = user_data.get('name', 'the user')
        # Use the injury field instead of pain_description
        pain_description = user_data.get('injury', '')
        print(f"📋 Using pain description for OpenAI: '{pain_description}'")
        
        # Use specified exercises or default to all RSI exercises
        exercises_to_use = exercises if exercises is not None else RSI_EXERCISES
        
        # If user has finger pain, prioritize finger exercises
        if pain_description and 'finger' in pain_description.lower():
            finger_exercises = [ex for ex in ALL_EXERCISES if 'finger' in ' '.join(ex.get('target_joints', [])).lower()]
            if finger_exercises:
                print(f"📋 Found {len(finger_exercises)} finger exercises based on injury")
                exercises_to_use = finger_exercises
        
        # Create a JSON string of all available exercises
        exercises_json = json.dumps(exercises_to_use)
        
        # Construct prompt for OpenAI
        prompt = f"""
        I need you to select the most appropriate exercise for a user with the following profile:
        
        Name: {name}
        Pain description: {pain_description}
        
        Below is a list of predefined exercises. Please select the ONE most appropriate exercise based on the user's pain description:
        
        {exercises_json}
        
        After selecting the most appropriate exercise, please provide detailed instructions for that specific exercise. The instructions should be clear, step-by-step, and tailored to the user's condition.
        
        Format your response as JSON:
        {{
          "selected_exercise": {{
            "name": "Exercise Name",
            "description": "Detailed description of the exercise and its benefits for this specific user",
            "target_joints": ["joint1", "joint2"],
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
                    {"role": "system", "content": "You are a senior physical therapist specializing in rehabilitation."},
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
        logger.info(f"OpenAI API response: {result}")  # Log the full response
        
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        logger.info(f"Extracted content: {content}")  # Log the extracted content
        
        # Try to clean the content if it contains markdown
        if '```json' in content:
            logger.info("Content contains markdown, cleaning...")
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
                logger.info(f"Cleaned content: {content}")
        
        try:
            response_data = json.loads(content)
            logger.info(f"Parsed JSON: {response_data}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            logger.error(f"Failed content: {content}")
            raise
        
        selected_exercise = response_data.get('selected_exercise', {})
        
        # Ensure all required fields are present
        if not all(key in selected_exercise for key in ['name', 'description', 'target_joints', 'instructions']):
            logger.warning("Missing required fields in LLM response, using fallback")
            return get_fallback_exercise(exercises_to_use)
        
        # Preserve videoURL from original exercise if available
        for exercise in exercises_to_use:
            if exercise['name'] == selected_exercise['name'] and 'videoURL' in exercise:
                selected_exercise['videoURL'] = exercise['videoURL']
                break
        
        return selected_exercise
    except Exception as e:
        logger.error(f"Error in select_exercise_with_openai: {str(e)}", exc_info=True)
        # Provide a fallback exercise in case of failure
        return get_fallback_exercise(exercises)

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

def get_fallback_exercise(exercises=None):
    """
    Return a fallback exercise when API calls fail
    """
    # Use the provided exercises list, or default to ALL_EXERCISES, or fall back to a hardcoded exercise
    if exercises and len(exercises) > 0:
        return exercises[0]
    elif len(ALL_EXERCISES) > 0:
        return ALL_EXERCISES[0]
    else:
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