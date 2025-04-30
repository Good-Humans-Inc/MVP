import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from openai import OpenAI
import json
from datetime import datetime, timedelta
from google.cloud import secretmanager
from google.cloud.firestore_v1._helpers import DatetimeWithNanoseconds
import uuid
import re

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
        user_id = request_json.get('user_id')
        exercise_id = request_json.get('exercise_id')
        conversation_history = request_json.get('conversation_history', [])
        
        # Debug logging
        print("Received request data:")
        print(f"User ID: {user_id}")
        print(f"Exercise ID: {exercise_id}")
        print("Conversation History:")
        print(json.dumps(conversation_history, indent=2))
        
        if not user_id or not exercise_id:
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
        streak_info = calculate_streak(user_id)
        
        # Extract exercise metrics from conversation
        metrics = extract_exercise_metrics(conversation_history)
        
        # Format conversation history for GPT
        formatted_history = format_conversation_history(conversation_history)
        
        # Create GPT prompt
        prompt = f"""Based on your exercise session conversation, here's your personalized physical therapy report:

Exercise: {exercise_data.get('name', 'Unknown')}
Date: {datetime.now().strftime('%Y-%m-%d')}

Your Progress:
- Your current streak: {streak_info['current_streak']} days in a row
- Your last exercise: {streak_info['last_exercise_date']}
- Your best streak: {streak_info['best_streak']} days

Your Exercise Stats:
Sets Completed: {metrics['sets_completed']}
Reps Completed: {metrics['reps_completed']}
Exercise Duration: {metrics['duration_minutes']} minutes

Your Conversation:
{formatted_history}

Please provide a personalized report in STRICT JSON format. Your response must be ONLY valid JSON with no additional text or explanation.

The JSON must have these exact keys and value types:
{{
    "general_feeling": "string describing your overall experience, focusing on specific achievements",
    "performance_quality": "string highlighting your technique strengths and specific areas for growth",
    "pain_report": "string addressing any discomfort with validation and actionable guidance",
    "completed": boolean,
    "sets_completed": number,
    "reps_completed": number,
    "day_streak": number,
    "motivational_message": "string with specific encouragement for next session"
}}

Guidelines for each field:
- Use direct "you/your" language
- Be very concise. Only use 1-2 sentences for each field.
- Focus on specific observations and achievements
- Provide actionable guidance
- Be encouraging and supportive
- Avoid speculative language ("seems like", "appears to")
- Keep each string field concise but detailed"""

        # Call OpenAI API with new format
        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": """You are a supportive physical therapist assistant specialized in RSI (Repetitive Strain Injury).
                Your task is to generate a JSON report that MUST be valid JSON.
                DO NOT include any additional text, markdown, or explanation outside the JSON structure.
                Use second-person pronouns (you/your) to speak directly to the user.
                Be encouraging while maintaining professionalism.
                Focus on specific achievements and actionable guidance.
                
                CRITICAL: Your entire response must be a single, valid JSON object."""},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }  # Enforce JSON response format
        )
        
        # Parse GPT response with better error handling
        try:
            response_content = response.choices[0].message.content.strip()
            print("Raw GPT response:")
            print(response_content)
            
            # Try to clean the response if it contains markdown code blocks
            if response_content.startswith('```json'):
                response_content = response_content.replace('```json', '').replace('```', '').strip()
            elif response_content.startswith('```'):
                response_content = response_content.replace('```', '').strip()
                
            report_data = json.loads(response_content)
            print("Parsed JSON response:")
            print(json.dumps(report_data, indent=2))
            
        except json.JSONDecodeError as e:
            print(f"Error parsing GPT response: {str(e)}")
            print("Raw GPT response:")
            print(response.choices[0].message.content)
            return (json.dumps({
                'error': 'Failed to parse GPT response',
                'details': str(e),
                'raw_response': response.choices[0].message.content
            }), 500, headers)
        
        # Update with actual metrics and streak
        report_data['sets_completed'] = metrics['sets_completed']
        report_data['reps_completed'] = metrics['reps_completed']
        report_data['day_streak'] = streak_info['current_streak']
        
        # Create a copy of report_data for Firestore
        firestore_data = report_data.copy()
        firestore_data.update({
            'user_id': user_id,
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
        
        # Update user's streak information
        update_user_streak(user_id, streak_info)
        
        # Generate next day's notification message using GPT
        try:
            # Get user's exercise history and preferences
            user_ref = db.collection('users').document(user_id)
            user_doc = user_ref.get()
            user_data = user_doc.to_dict()
            
            # Get next notification time
            next_notification_time = user_data.get('next_notification_time')
            readable_time = "your scheduled time"
            
            # Format next notification time if available
            if next_notification_time:
                # Handle Firestore timestamp or datetime
                if hasattr(next_notification_time, 'datetime'):
                    time_obj = next_notification_time.datetime
                else:
                    time_obj = next_notification_time
                    
                # Format as AM/PM for better readability
                hour = time_obj.hour
                minute = time_obj.minute
                am_pm = "AM" if hour < 12 else "PM"
                display_hour = hour if hour <= 12 else hour - 12
                if display_hour == 0:
                    display_hour = 12
                readable_time = f"{display_hour}:{minute:02d} {am_pm}"
                print(f"📅 Next notification scheduled for: {readable_time}")
            else:
                print("⚠️ No next_notification_time found in user data")
            
            # Get user's exercises
            user_exercises = db.collection('user_exercises').where('user_id', '==', user_id).get()
            exercise_names = []
            for doc in user_exercises:
                ex_data = doc.to_dict()
                ex_id = ex_data.get('exercise_id')
                if ex_id:
                    ex_doc = db.collection('exercises').document(ex_id).get()
                    if ex_doc.exists:
                        ex_data = ex_doc.to_dict()
                        exercise_names.append(ex_data.get('name', 'Unknown'))
            
            # Generate personalized notification content
            notification_content = generate_notification_content(
                user_name=user_data.get('name', 'User'),
                exercise_names=exercise_names,
                user_data=user_data
            )
            
            # Save to user's document for next day use
            next_notification_update = {
                'next_day_notification': {
                    'title': notification_content['title'],
                    'body': notification_content['body'],
                    'created_at': firestore.SERVER_TIMESTAMP
                }
            }
            
            # Add next_notification_time if available
            if next_notification_time:
                next_notification_update['next_day_notification']['scheduled_time'] = next_notification_time
                
            user_ref.update(next_notification_update)
            
            print(f"✅ Generated and stored next day notification message for user {user_id}")
            
        except Exception as e:
            print(f"⚠️ Error generating notification message: {str(e)}")
            # Continue with report generation even if notification generation fails
        
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

def calculate_streak(user_id):
    """Calculate user's exercise streak."""
    today = datetime.now().date()
    
    # Get user's exercise reports ordered by date
    reports = db.collection('exercise_reports') \
        .where('user_id', '==', user_id) \
        .order_by('timestamp', direction=firestore.Query.DESCENDING) \
        .get()
    
    if not reports:
        return {
            'current_streak': 1,  # Count today's exercise
            'best_streak': 1,
            'last_exercise_date': today.strftime('%Y-%m-%d')
        }
    
    # Get user's streak info
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()
    best_streak = 1
    
    if user_doc.exists:
        user_data = user_doc.to_dict()
        best_streak = user_data.get('best_streak', 1)
    
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

def update_user_streak(user_id, streak_info):
    """Update user's streak information in Firestore."""
    user_ref = db.collection('users').document(user_id)
    
    # Create a copy of streak_info for Firestore
    firestore_data = {
        'current_streak': streak_info['current_streak'],
        'best_streak': streak_info['best_streak'],
        'last_exercise_date': streak_info['last_exercise_date'],
        'last_updated': firestore.SERVER_TIMESTAMP
    }
    
    user_ref.set(firestore_data, merge=True)

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

def generate_notification_content(user_name, exercise_names, user_data):
    """Generate personalized notification content using OpenAI."""
    try:
        client = OpenAI(api_key=get_secret('openai-api-key'))
        
        # Get user's preferences and history
        preferred_tone = user_data.get('notification_preferences', {}).get('tone', 'friendly')
        exercise_history = user_data.get('exercise_history', [])
        streak = len(exercise_history)
        
        # Get next notification time
        next_notification_time = user_data.get('next_notification_time')
        readable_time = "your scheduled time"
        
        # Format next notification time if available
        if next_notification_time:
            # Handle Firestore timestamp or datetime
            if hasattr(next_notification_time, 'datetime'):
                time_obj = next_notification_time.datetime
            else:
                time_obj = next_notification_time
                
            # Format as AM/PM for better readability
            hour = time_obj.hour
            minute = time_obj.minute
            am_pm = "AM" if hour < 12 else "PM"
            display_hour = hour if hour <= 12 else hour - 12
            if display_hour == 0:
                display_hour = 12
            readable_time = f"{display_hour}:{minute:02d} {am_pm}"
        
        # Create prompt for OpenAI
        prompt = f"""Generate a motivational exercise reminder notification for a physical therapy user with the following details:

User Name: {user_name}
Exercises: {', '.join(exercise_names)}
Current Streak: {streak} days
Preferred Tone: {preferred_tone}
Next Notification Time: {readable_time}

The notification should have:
1. A catchy title (max 44 characters)
2. A motivational message (max 150 characters)
3. Be {preferred_tone} in tone
4. Mention specific exercises if provided
5. Include streak information if significant (>3 days)
6. If relevant, reference the scheduled time ({readable_time})

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
            "body": f"Hi {user_name}! Ready to continue your progress? Let's work on your exercises today!"
        }

# Update the send_exercise_notification function to use OpenAI-generated content
def send_exercise_notification(user_id, fcm_token):
    """Send an exercise reminder notification to a user's device via FCM"""
    # Get user details
    user_doc = db.collection('users').document(user_id).get()
    user_data = user_doc.to_dict()
    user_name = user_data.get('name', 'User')
    
    # Get user exercises
    user_exercises = db.collection('user_exercises').where('user_id', '==', user_id).get()
    exercise_ids = [doc.to_dict().get('exercise_id') for doc in user_exercises]
    
    # Get exercise details
    exercise_names = []
    for ex_id in exercise_ids:
        ex_doc = db.collection('exercises').document(ex_id).get()
        if ex_doc.exists:
            ex_data = ex_doc.to_dict()
            exercise_names.append(ex_data.get('name'))
    
    # Generate notification content using OpenAI
    notification_content = generate_notification_content(user_name, exercise_names, user_data)
    
    # Create notification content
    title = notification_content['title']
    body = notification_content['body']
    
    # Save notification to database
    notification_id = str(uuid.uuid4())
    notification = {
        'id': notification_id,
        'user_id': user_id,
        'title': title,
        'body': body,
        'scheduled_for': datetime.now(),
        'exercise_ids': exercise_ids,
        'status': 'sending',
        'created_at': datetime.now(),
        'content_type': 'ai_generated'
    }