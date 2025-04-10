import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from openai import OpenAI
import json
from datetime import datetime, timedelta
from google.cloud import secretmanager
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
import uuid

# Initialize Firebase Admin with default credentials
firebase_admin.initialize_app()
db = db = firestore.Client(project='pepmvp', database='pep-mvp')

def get_secret(secret_id):
    """Get secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/pepmvp/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

@functions_framework.http
def generate_report(request):
    # Enable CORS
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    try:
        # Initialize OpenAI client with API key from Secret Manager
        client = OpenAI(api_key=get_secret('openai-api-key'))
        
        # Get request data
        request_json = request.get_json()
        patient_id = request_json.get('patient_id')
        exercise_id = request_json.get('exercise_id')
        conversation_history = request_json.get('conversation_history', [])
        
        # Debug logging
        print("Received request data:")
        print(f"Patient ID: {patient_id}")
        print(f"Exercise ID: {exercise_id}")
        print("Conversation History:")
        print(json.dumps(conversation_history, indent=2))
        
        if not patient_id or not exercise_id:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Convert exercise_id to uppercase for consistency
        exercise_id = exercise_id.upper()
        print(f"Normalized Exercise ID: {exercise_id}")
        
        # Get exercise details from Firestore
        exercise_ref = db.collection('exercises').document(exercise_id)
        exercise_doc = exercise_ref.get()
        
        if not exercise_doc.exists:
            # Try a case-insensitive search
            print("Exercise not found with exact ID, trying case-insensitive search...")
            exercises_query = db.collection('exercises').get()
            found_doc = None
            for doc in exercises_query:
                if doc.id.upper() == exercise_id.upper():
                    found_doc = doc
                    break
            
            if found_doc is None:
                print(f"Exercise not found with ID: {exercise_id}")
                return (json.dumps({'error': 'Exercise not found'}), 404, headers)
            else:
                print(f"Found exercise with case-insensitive match: {found_doc.id}")
                exercise_doc = found_doc
        
        exercise_data = exercise_doc.to_dict()
        # Serialize exercise data for logging
        serialized_exercise_data = serialize_firestore_data(exercise_data)
        print(f"Found exercise data: {json.dumps(serialized_exercise_data, indent=2)}")
            
        # Calculate streak information
        streak_info = calculate_streak(patient_id)
        
        # Extract exercise metrics from conversation
        metrics = extract_exercise_metrics(conversation_history)
        
        # Format conversation history for GPT
        formatted_history = format_conversation_history(conversation_history)
        
        # Create GPT prompt
        prompt = f"""Based on the following exercise session conversation, generate a comprehensive physical therapy report:

Exercise: {exercise_data.get('name', 'Unknown')}
Date: {datetime.now().strftime('%Y-%m-%d')}

Current Streak Information:
- Days in a row: {streak_info['current_streak']}
- Last exercise: {streak_info['last_exercise_date']}
- Best streak: {streak_info['best_streak']}

Exercise Metrics:
Sets Completed: {metrics['sets_completed']}
Reps Completed: {metrics['reps_completed']}
Exercise Duration: {metrics['duration_minutes']} minutes

Conversation History:
{formatted_history}

Please analyze the conversation and provide a detailed report including:

1. General Feeling: Patient's overall experience and engagement during the session
2. Performance Quality: Assessment of exercise execution and technique
3. Pain Report: Any pain or discomfort mentioned
4. Completion Status: Whether the exercise was completed as prescribed
5. Sets and Reps Completed: Actual exercise volume achieved
6. Day Streak: Current streak with encouraging note about consistency
7. Motivational Message: Personalized encouragement based on performance and streak

Format the response as JSON with these exact keys:
{{
    "general_feeling": "string",
    "performance_quality": "string",
    "pain_report": "string",
    "completed": boolean,
    "sets_completed": integer,
    "reps_completed": integer,
    "day_streak": integer,
    "motivational_message": "string"
}}"""

        # Call OpenAI API with new format
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """You are a professional physical therapist assistant specialized in RSI (Repetitive Strain Injury).
                Generate detailed reports based on exercise conversations.
                Focus on form, technique, and pain management.
                Be encouraging but maintain professionalism.
                Pay special attention to any mentions of discomfort or pain."""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # Parse GPT response
        try:
            report_data = json.loads(response.choices[0].message.content)
            print("GPT Response:")
            print(json.dumps(report_data, indent=2))
        except json.JSONDecodeError as e:
            print(f"Error parsing GPT response: {str(e)}")
            print("Raw GPT response:")
            print(response.choices[0].message.content)
            return (json.dumps({'error': 'Failed to parse GPT response'}), 500, headers)
        
        # Update with actual metrics and streak
        report_data['sets_completed'] = metrics['sets_completed']
        report_data['reps_completed'] = metrics['reps_completed']
        report_data['day_streak'] = streak_info['current_streak']
        
        # Create a copy of report_data for Firestore
        firestore_data = report_data.copy()
        firestore_data.update({
            'patient_id': patient_id,
            'exercise_id': exercise_id,
            'timestamp': firestore.SERVER_TIMESTAMP,
            'exercise_name': exercise_data.get('name', 'Unknown'),
            'exercise_description': exercise_data.get('description', ''),
            'target_joints': exercise_data.get('target_joints', []),
            'instructions': exercise_data.get('instructions', []),
            'duration_minutes': metrics['duration_minutes'],
            'best_streak': streak_info['best_streak']
        })
        
        # Store report in Firestore
        report_ref = db.collection('exercise_reports').document()
        report_ref.set(firestore_data)
        
        # Update patient's streak information
        update_patient_streak(patient_id, streak_info)
        
        # Add timestamp to the response data (use ISO format string directly)
        report_data['timestamp'] = datetime.now().isoformat()
        
        # Prepare response
        response_data = {
            'status': 'success',
            'report_id': report_ref.id,
            'report': report_data
        }
        
        # Ensure all Firestore timestamps are serialized
        try:
            serialized_response = serialize_firestore_data(response_data)
            json_response = json.dumps(serialized_response)
            print("Final Response:")
            print(json.dumps(serialized_response, indent=2))
            return (json_response, 200, headers)
        except Exception as e:
            print(f"Error serializing response: {str(e)}")
            # Fallback to a simpler response if serialization fails
            fallback_response = {
                'status': 'success',
                'report_id': report_ref.id,
                'report': {
                    **report_data,
                    'timestamp': datetime.now().isoformat()
                }
            }
            return (json.dumps(fallback_response), 200, headers)
        
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        return (json.dumps({'error': str(e)}), 500, headers)

def calculate_streak(patient_id):
    """Calculate patient's exercise streak."""
    today = datetime.now().date()
    
    # Get patient's exercise reports ordered by date
    reports = db.collection('exercise_reports') \
        .where('patient_id', '==', patient_id) \
        .order_by('timestamp', direction=firestore.Query.DESCENDING) \
        .get()
    
    if not reports:
        return {
            'current_streak': 1,  # Count today's exercise
            'best_streak': 1,
            'last_exercise_date': today.strftime('%Y-%m-%d')
        }
    
    # Get patient's streak info
    patient_ref = db.collection('patients').document(patient_id)
    patient_doc = patient_ref.get()
    best_streak = 1
    
    if patient_doc.exists:
        patient_data = patient_doc.to_dict()
        best_streak = patient_data.get('best_streak', 1)
    
    # Calculate current streak
    current_streak = 1  # Start with today
    last_date = today
    
    for report in reports:
        report_data = report.to_dict()
        timestamp = report_data.get('timestamp')
        if timestamp:
            # Handle both DatetimeWithNanoseconds and Timestamp types
            if hasattr(timestamp, 'date'):
                report_date = timestamp.date()
            else:
                report_date = timestamp.datetime.date()
        else:
            continue
        
        # If this exercise was done today, skip to next
        if report_date == today:
            continue
            
        # If this exercise was done yesterday, increment streak
        if report_date == last_date - timedelta(days=1):
            current_streak += 1
            last_date = report_date
        else:
            break
    
    return {
        'current_streak': current_streak,
        'best_streak': max(best_streak, current_streak),
        'last_exercise_date': last_date.strftime('%Y-%m-%d')
    }

def update_patient_streak(patient_id, streak_info):
    """Update patient's streak information in Firestore."""
    patient_ref = db.collection('patients').document(patient_id)
    
    # Create a copy of streak_info for Firestore
    firestore_data = {
        'current_streak': streak_info['current_streak'],
        'best_streak': streak_info['best_streak'],
        'last_exercise_date': streak_info['last_exercise_date'],
        'last_updated': firestore.SERVER_TIMESTAMP
    }
    
    patient_ref.set(firestore_data, merge=True)

def extract_exercise_metrics(conversation_history):
    """Extract exercise metrics from conversation history."""
    metrics = {
        'sets_completed': 0,
        'reps_completed': 0,
        'duration_minutes': 0
    }
    
    for message in conversation_history:
        content = message.get('content', '').lower()
        
        # Look for sets completed
        if 'set' in content or 'sets' in content:
            import re
            set_matches = re.findall(r'(\d+)\s*sets?', content)
            if set_matches:
                metrics['sets_completed'] = max(metrics['sets_completed'], int(set_matches[-1]))
        
        # Look for reps completed
        if 'rep' in content or 'reps' in content:
            rep_matches = re.findall(r'(\d+)\s*reps?', content)
            if rep_matches:
                metrics['reps_completed'] = max(metrics['reps_completed'], int(rep_matches[-1]))
        
        # Look for duration
        if 'minute' in content or 'minutes' in content:
            duration_matches = re.findall(r'(\d+)\s*minutes?', content)
            if duration_matches:
                metrics['duration_minutes'] = max(metrics['duration_minutes'], int(duration_matches[-1]))
    
    # Set defaults if no metrics found
    if metrics['sets_completed'] == 0:
        metrics['sets_completed'] = 3
    if metrics['reps_completed'] == 0:
        metrics['reps_completed'] = 10
    if metrics['duration_minutes'] == 0:
        metrics['duration_minutes'] = 5
    
    return metrics

def format_conversation_history(conversation_history):
    """Format conversation history for GPT prompt."""
    formatted = []
    for message in conversation_history:
        role = message.get('role', 'user')
        content = message.get('content', '')
        formatted.append(f"{role.capitalize()}: {content}")
    return "\n".join(formatted)

def serialize_firestore_data(data):
    """Helper function to serialize Firestore data for JSON."""
    if isinstance(data, dict):
        return {k: serialize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_firestore_data(item) for item in data]
    elif isinstance(data, DatetimeWithNanoseconds):
        return data.isoformat()
    elif hasattr(data, 'datetime'):  # Handle Firestore Timestamp
        return data.datetime.isoformat()
    else:
        return data

def generate_notification_content(patient_name, exercise_names, patient_data):
    """Generate personalized notification content using OpenAI."""
    try:
        client = OpenAI(api_key=get_secret('openai-api-key'))
        
        # Get patient's preferences and history
        preferred_tone = patient_data.get('notification_preferences', {}).get('tone', 'friendly')
        exercise_history = patient_data.get('exercise_history', [])
        streak = len(exercise_history)
        
        # Create prompt for OpenAI
        prompt = f"""Generate a motivational exercise reminder notification for a physical therapy patient with the following details:

Patient Name: {patient_name}
Exercises: {', '.join(exercise_names)}
Current Streak: {streak} days
Preferred Tone: {preferred_tone}

The notification should have:
1. A catchy title (max 50 characters)
2. A motivational message (max 150 characters)
3. Be {preferred_tone} in tone
4. Mention specific exercises if provided
5. Include streak information if significant (>3 days)

Format the response as JSON:
{{
    "title": "string",
    "body": "string"
}}"""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a motivational physical therapy assistant crafting engaging notifications."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        # Parse the response
        content = json.loads(response.choices[0].message.content)
        return content
        
    except Exception as e:
        print(f"Error generating notification content: {str(e)}")
        # Return default content if OpenAI generation fails
        return {
            "title": "Time for your PT exercises!",
            "body": f"Hi {patient_name}! Ready to continue your progress? Let's work on your exercises today!"
        }

# Update the send_exercise_notification function to use OpenAI-generated content
def send_exercise_notification(patient_id, fcm_token):
    """Send an exercise reminder notification to a patient's device via FCM"""
    # Get patient details
    patient_doc = db.collection('patients').document(patient_id).get()
    patient_data = patient_doc.to_dict()
    patient_name = patient_data.get('name', 'Patient')
    
    # Get patient exercises
    patient_exercises = db.collection('patient_exercises').where('patient_id', '==', patient_id).get()
    exercise_ids = [doc.to_dict().get('exercise_id') for doc in patient_exercises]
    
    # Get exercise details
    exercise_names = []
    for ex_id in exercise_ids:
        ex_doc = db.collection('exercises').document(ex_id).get()
        if ex_doc.exists:
            ex_data = ex_doc.to_dict()
            exercise_names.append(ex_data.get('name'))
    
    # Generate notification content using OpenAI
    notification_content = generate_notification_content(patient_name, exercise_names, patient_data)
    
    # Create notification content
    title = notification_content['title']
    body = notification_content['body']
    
    # Save notification to database
    notification_id = str(uuid.uuid4())
    notification = {
        'id': notification_id,
        'patient_id': patient_id,
        'title': title,
        'body': body,
        'scheduled_for': datetime.now(),
        'exercise_ids': exercise_ids,
        'status': 'sending',
        'created_at': datetime.now(),
        'content_type': 'ai_generated'
    }
    
    # ... rest of the existing send_exercise_notification function ...
