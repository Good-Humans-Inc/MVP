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
db = firestore.Client()

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
        project_id = "duoligo-pt-app"  # Replace with your project ID
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        # Strip whitespace and newlines to avoid issues with API keys
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error accessing secret '{secret_id}': {str(e)}")
        raise

@functions_framework.http
def generate_exercises(request):
    """
    Cloud Function to generate a single recommended exercise for a patient.
    
    Request format:
    {
        "patient_id": "uuid-of-patient",
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
        
        if not request_json or 'patient_id' not in request_json:
            return (json.dumps({'error': 'Invalid request - missing patient_id'}, cls=DateTimeEncoder), 400, headers)
        
        patient_id = request_json['patient_id']
        llm_provider = request_json.get('llm_provider', 'openai')  # Default to OpenAI
        
        logger.info(f"Processing request for patient_id: {patient_id}, llm_provider: {llm_provider}")
        
        # Get API keys
        if llm_provider == 'claude':
            api_key = access_secret_version("anthropic-api-key")
        else:
            api_key = access_secret_version("openai-api-key")
        
        # Google API keys for YouTube video search
        google_api_key = access_secret_version("google-api-key")
        google_cse_id = access_secret_version("google-cse-id")
        
        # Get patient data
        patient_data = get_patient_data(patient_id)
        if not patient_data:
            logger.warning(f"Patient not found: {patient_id}")
            return (json.dumps({'error': 'Patient not found'}, cls=DateTimeEncoder), 404, headers)
        
        # Generate a recommended exercise
        if llm_provider == 'claude':
            exercise = generate_exercise_with_claude(patient_data, api_key)
        else:
            exercise = generate_exercise_with_openai(patient_data, api_key)
        
        logger.info(f"Generated exercise: {exercise['name']}")
        
        # Find a YouTube video for the exercise
        enhanced_exercise = enhance_exercise_with_video(exercise, google_api_key, google_cse_id)
        
        # Save the exercise to Firestore
        saved_exercise = save_exercise(enhanced_exercise, patient_id)
        
        # Return success
        return (json.dumps({
            'status': 'success',
            'exercise': saved_exercise,
            'source': 'llm-generated'
        }, cls=DateTimeEncoder), 200, headers)
        
    except Exception as e:
        logger.error(f"Error generating exercise: {str(e)}", exc_info=True)
        return (json.dumps({'error': f'Error generating exercise: {str(e)}'}, cls=DateTimeEncoder), 500, headers)


def get_patient_data(patient_id):
    """
    Retrieve patient data from Firestore
    """
    # Get patient document
    patient_doc = db.collection('patients').document(patient_id).get()
    
    if not patient_doc.exists:
        return None
    
    return patient_doc.to_dict()


def generate_exercise_with_claude(patient_data, api_key):
    """
    Generate a single recommended exercise using Anthropic's Claude API
    """
    try:
        # Extract patient info
        name = patient_data.get('name', 'the patient')
        age = patient_data.get('age', 0)
        pain_description = patient_data.get('pain_description', 'knee pain')
        pain_level = patient_data.get('pain_level', 5)
        
        # Construct prompt for Claude
        prompt = f"""
        I need ONE appropriate knee rehabilitation exercise for a patient with the following profile:
        
        Name: {name}
        Age: {age}
        Pain description: {pain_description}
        Pain level: {pain_level}/10
        
        Please provide 1 evidence-based exercise that would be appropriate for this patient.
        Consider standard physical therapy protocols and clinical practice guidelines.
        
        The exercise should include:
        1. A clear name
        2. A concise description
        3. Target joints (as a list of: knee, ankle, hip)
        4. Step-by-step instructions (as a list)
        
        Format your response as JSON:
        {{
          "name": "Exercise Name",
          "description": "Brief description of the exercise",
          "target_joints": ["knee", "ankle"],
          "instructions": [
            "Step 1",
            "Step 2",
            "Step 3"
          ]
        }}
        
        Respond ONLY with the JSON object and nothing else.
        """
        
        logger.info("Calling Claude API to generate exercise")
        
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
                "system": "You are a senior physical therapist specializing in knee rehabilitation.",
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
        
        exercise = json.loads(exercise_json)
        
        return exercise
    except Exception as e:
        logger.error(f"Error in generate_exercise_with_claude: {str(e)}", exc_info=True)
        # Provide a fallback exercise in case of failure
        return get_fallback_exercise()


def generate_exercise_with_openai(patient_data, api_key):
    """
    Generate a single recommended exercise using OpenAI's GPT API
    """
    try:
        # Extract patient info
        name = patient_data.get('name', 'the patient')
        age = patient_data.get('age', 0)
        pain_description = patient_data.get('pain_description', 'knee pain')
        pain_level = patient_data.get('pain_level', 5)
        
        # Construct prompt for OpenAI
        prompt = f"""
        I need ONE appropriate knee rehabilitation exercise for a patient with the following profile:
        
        Name: {name}
        Age: {age}
        Pain description: {pain_description}
        Pain level: {pain_level}/10
        
        Please provide 1 evidence-based exercise that would be appropriate for this patient.
        Consider standard physical therapy protocols and clinical practice guidelines.
        
        The exercise should include:
        1. A clear name
        2. A concise description
        3. Target joints (as a list of: knee, ankle, hip)
        4. Step-by-step instructions (as a list)
        
        Format your response as JSON:
        {{
          "name": "Exercise Name",
          "description": "Brief description of the exercise",
          "target_joints": ["knee", "ankle"],
          "instructions": [
            "Step 1",
            "Step 2",
            "Step 3"
          ]
        }}
        
        Respond ONLY with the JSON object and nothing else.
        """
        
        logger.info("Calling OpenAI API to generate exercise")
        
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
                    {"role": "system", "content": "You are a senior physical therapist specializing in knee rehabilitation."},
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
        
        exercise = json.loads(content)
        
        return exercise
    except Exception as e:
        logger.error(f"Error in generate_exercise_with_openai: {str(e)}", exc_info=True)
        # Provide a fallback exercise in case of failure
        return get_fallback_exercise()


def enhance_exercise_with_video(exercise, google_api_key, google_cse_id):
    """
    Add a YouTube video URL and thumbnail to the exercise
    """
    try:
        # Create search query for exercise videos
        search_query = f"{exercise['name']} knee physical therapy exercise"
        logger.info(f"Searching for videos: '{search_query}'")
        
        video_data = search_youtube_video(search_query, google_api_key, google_cse_id)
        
        # Add video data to exercise
        exercise_with_video = exercise.copy()
        
        if video_data:
            exercise_with_video['video_url'] = video_data.get('video_url', '')
            exercise_with_video['video_thumbnail'] = video_data.get('thumbnail', '')
            
            # Validate the found video
            if not validate_video_url(exercise_with_video['video_url']):
                # Try a more specific search
                alt_search_query = f"{exercise['name']} knee rehabilitation exercise demonstration"
                alt_video_data = search_youtube_video(alt_search_query, google_api_key, google_cse_id, num_results=3)
                
                if alt_video_data:
                    exercise_with_video['video_url'] = alt_video_data.get('video_url', '')
                    exercise_with_video['video_thumbnail'] = alt_video_data.get('thumbnail', '')
                    logger.info(f"Alternative search found video: {exercise_with_video['video_url']}")
            else:
                logger.info(f"Found valid video: {exercise_with_video['video_url']}")
        else:
            # Fallback if no video found
            logger.warning(f"❌ No video found for '{exercise['name']}'")
            exercise_with_video['video_url'] = ''
            exercise_with_video['video_thumbnail'] = ''
        
        return exercise_with_video
    except Exception as e:
        logger.error(f"Error enhancing exercise with video: {str(e)}", exc_info=True)
        # Return original exercise if enhancement fails
        return exercise


def search_youtube_video(query, google_api_key, google_cse_id, num_results=1):
    """
    Search for YouTube videos using Google Custom Search API and return the URL and thumbnail
    """
    try:
        # Build the API request
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': google_api_key,
            'cx': google_cse_id,
            'q': query + " youtube",
            'num': num_results
        }
        
        logger.info(f"Calling Google Custom Search API with query: '{query} youtube'")
        
        # Make the API request
        response = requests.get(url, params=params)
        
        # Check for errors
        if response.status_code != 200:
            logger.error(f"Google Search API error: {response.text}")
            return None
        
        # Process the response
        data = response.json()
        
        # Check if we got search results
        if 'items' not in data or len(data['items']) == 0:
            logger.warning("No search results found")
            return None
        
        # Get all video results
        all_videos = []
        for idx, item in enumerate(data['items']):
            video_url = item.get('link', '')
            
            # Check if this is a YouTube link
            is_youtube = 'youtube.com' in video_url or 'youtu.be' in video_url
            
            # Only process YouTube links
            if not is_youtube:
                continue
                
            # Get thumbnail image if available
            thumbnail = ''
            if 'pagemap' in item:
                if 'cse_image' in item['pagemap']:
                    thumbnail = item['pagemap']['cse_image'][0].get('src', '')
                elif 'videoobject' in item['pagemap']:
                    thumbnail = item['pagemap']['videoobject'][0].get('thumbnailurl', '')
            
            # If no thumbnail found, generate one from YouTube video ID
            if not thumbnail and is_youtube:
                video_id = extract_youtube_video_id(video_url)
                if video_id:
                    thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            
            all_videos.append({
                'title': item.get('title', 'Unknown'),
                'video_url': video_url,
                'thumbnail': thumbnail
            })
        
        # If we have YouTube results
        if all_videos:
            # Return the first result
            return all_videos[0]
        else:
            logger.warning("No YouTube videos found in search results")
            return None
            
    except Exception as e:
        logger.error(f"Error searching for video: {str(e)}", exc_info=True)
        return None


def validate_video_url(url):
    """
    Check if a YouTube video URL is valid
    """
    if not url:
        return False
        
    try:
        if 'youtube.com' in url or 'youtu.be' in url:
            # Extract video ID
            video_id = extract_youtube_video_id(url)
            
            if not video_id:
                return False
                
            # Check video info via oEmbed API (lightweight way to validate)
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            response = requests.get(oembed_url)
            
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"Error validating video URL {url}: {str(e)}")
    
    return False


def extract_youtube_video_id(url):
    """
    Extract the video ID from a YouTube URL
    """
    if not url:
        return None
        
    # Match pattern for various YouTube URL formats
    pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(pattern, url)
    
    if match:
        return match.group(1)
    return None


def save_exercise(exercise, patient_id):
    """
    Save the exercise to Firestore and link it to the patient
    """
    # Add required fields
    exercise_id = str(uuid.uuid4())
    timestamp = datetime.now()
    
    # Format the data for Firestore
    exercise_data = {
        'id': exercise_id,
        'name': exercise.get('name', 'Knee Exercise'),
        'description': exercise.get('description', ''),
        'target_joints': exercise.get('target_joints', ['knee']),
        'instructions': exercise.get('instructions', []),
        'video_url': exercise.get('video_url', ''),
        'video_thumbnail': exercise.get('video_thumbnail', ''),
        'created_at': timestamp,
        'is_template': False,
        'source': 'llm-generated'
    }
    
    # Save to Firestore
    db.collection('exercises').document(exercise_id).set(exercise_data)
    
    # Create patient-exercise link
    patient_exercise_id = str(uuid.uuid4())
    patient_exercise = {
        'id': patient_exercise_id,
        'patient_id': patient_id,
        'exercise_id': exercise_id,
        'recommended_at': timestamp,
        'frequency': 'daily',  # Default
        'sets': 3,             # Default
        'repetitions': 10      # Default
    }
    
    db.collection('patient_exercises').document(patient_exercise_id).set(patient_exercise)
    
    return exercise_data


def get_fallback_exercise():
    """
    Return a fallback exercise when API calls fail
    """
    return {
        "name": "Seated Knee Extensions",
        "description": "A gentle exercise to strengthen the quadriceps muscles that support the knee joint.",
        "target_joints": ["knee"],
        "instructions": [
            "Sit on a chair with your back straight and feet flat on the floor",
            "Slowly extend your right leg until it's straight, keeping your thigh on the chair",
            "Hold for 5 seconds, focusing on tightening your thigh muscle",
            "Slowly lower your foot back to the floor",
            "Repeat 10 times, then switch to your left leg"
        ]
    }