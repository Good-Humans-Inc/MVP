# Update Information Cloud Function

This cloud function is designed to be called by the ElevenLabs agent to update user information in the Physical Therapy app. It handles updating notification preferences, ultimate goals, and exercise routines.

## Functionality

The `update_information` function allows the ElevenLabs agent to:

1. Update notification preferences (time and frequency)
2. Set or update the user's ultimate goal
3. Update the user's exercise routine

## API Endpoint

```
POST /update_information
```

## Request Format

```json
{
  "patient_id": "user123",
  "notification_time": "09:00",  // Optional, format: "HH:MM"
  "ultimate_goal": "Improve knee mobility and reduce pain",  // Optional
  "exercise_routine": [  // Optional
    {
      "name": "Knee Flexion",
      "description": "Gently bend and extend your knee to improve range of motion",
      "duration": 180,  // Optional, in seconds
      "target_joints": ["right_knee", "right_ankle", "right_hip"],  // Optional
      "instructions": [  // Optional
        "Sit on a chair with your feet flat on the floor",
        "Slowly lift your right foot and bend your knee",
        "Hold for 5 seconds",
        "Slowly lower your foot back to the floor",
        "Repeat 10 times"
      ]
    }
  ]
}
```

## Response Format

### Success Response

```json
{
  "status": "success",
  "message": "Patient information updated successfully",
  "updated_fields": ["notification_preferences", "ultimate_goal", "exercise_routine"]
}
```

### Error Response

```json
{
  "error": "Error message here"
}
```

## Integration with Other Functions

When notification preferences are updated, this function automatically:

1. Updates the user's profile in Firestore
2. Creates an activity log entry
3. Calls the `schedule_notification` function to schedule a notification at the specified time

## Firestore Collections

This function interacts with the following Firestore collections:

- `patients`: Contains patient information including notification preferences and exercise routines
- `activities`: Logs all profile updates and changes

## Usage by ElevenLabs Agent

The ElevenLabs agent can call this function to update user information based on conversation context. For example:

1. When a user mentions their preferred exercise time
2. When a user discusses their rehabilitation goals
3. When a user needs a customized exercise routine

## Deployment

To deploy this function to Firebase:

```bash
firebase deploy --only functions:update_information
``` 