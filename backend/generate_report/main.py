import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
import openai
import json
from datetime import datetime, timedelta
from google.cloud import secretmanager

# Initialize Firebase Admin
cred = credentials.Certificate('service-account.json')
firebase_admin.initialize_app(cred)
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
        # Get OpenAI API key from Secret Manager
        openai.api_key = get_secret('openai-api-key')
        
        # Get request data
        request_json = request.get_json()
        patient_id = request_json.get('patient_id')
        exercise_id = request_json.get('exercise_id')
        conversation_history = request_json.get('conversation_history', [])
        
        if not patient_id or not exercise_id:
            return (json.dumps({'error': 'Missing required parameters'}), 400, headers)
        
        # Get exercise details from Firestore
        exercise_ref = db.collection('exercises').document(exercise_id)
        exercise_doc = exercise_ref.get()
        
        if not exercise_doc.exists:
            return (json.dumps({'error': 'Exercise not found'}), 404, headers)
            
        exercise_data = exercise_doc.to_dict()
        
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

        # Call OpenAI API
        response = openai.ChatCompletion.create(
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
        report_data = json.loads(response.choices[0].message.content)
        
        # Update with actual metrics and streak
        report_data['sets_completed'] = metrics['sets_completed']
        report_data['reps_completed'] = metrics['reps_completed']
        report_data['day_streak'] = streak_info['current_streak']
        
        # Store report in Firestore
        report_ref = db.collection('exercise_reports').document()
        report_data.update({
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
        report_ref.set(report_data)
        
        # Update patient's streak information
        update_patient_streak(patient_id, streak_info)
        
        return (json.dumps({
            'status': 'success',
            'report_id': report_ref.id,
            'report': report_data
        }), 200, headers)
        
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
        report_date = report.get('timestamp').date()
        
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
    
    patient_ref.set({
        'current_streak': streak_info['current_streak'],
        'best_streak': streak_info['best_streak'],
        'last_exercise_date': streak_info['last_exercise_date'],
        'last_updated': firestore.SERVER_TIMESTAMP
    }, merge=True)

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
        metrics['duration_minutes'] = 3
    
    return metrics

def format_conversation_history(conversation_history):
    """Format conversation history for better GPT analysis."""
    formatted_messages = []
    for msg in conversation_history:
        role = msg.get('role', '')
        content = msg.get('content', '')
        speaker = 'Patient' if role == 'user' else 'AI Coach'
        formatted_messages.append(f"{speaker}: {content}")
    
    return "\n".join(formatted_messages)
