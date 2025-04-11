# Cloud Function Test Tools

This document provides instructions on how to use the test tools for the cloud functions in this project.

## Prerequisites

Before using these test tools, make sure you have the following installed:

1. Python 3.6 or higher
2. The `requests` library (`pip install requests`)

## Test Tools Overview

The following test tools are available:

1. `update_information/test_function.py` - Test the update_information cloud function
2. `schedule_notification/test_function.py` - Test the schedule_notification cloud function
3. `schedule_notification/test_update_fcm_token.py` - Test the update_fcm_token function

## Testing the update_information Function

The `update_information` function allows the ElevenLabs agent to update user information, including notification preferences, ultimate goals, and exercise routines.

### Basic Usage

```bash
python backend/update_information/test_function.py --base-url "http://localhost:8080" --patient-id "user123"
```

### Update Notification Time

```bash
python backend/update_information/test_function.py --base-url "http://localhost:8080" --patient-id "user123" --notification-time "09:00"
```

### Update Ultimate Goal

```bash
python backend/update_information/test_function.py --base-url "http://localhost:8080" --patient-id "user123" --ultimate-goal "Improve knee mobility and reduce pain"
```

### Update Exercise Routine

```bash
python backend/update_information/test_function.py --base-url "http://localhost:8080" --patient-id "user123" --exercise-routine "backend/update_information/sample_exercise_routine.json"
```

### Update All Information

```bash
python backend/update_information/test_function.py --base-url "http://localhost:8080" --patient-id "user123" --notification-time "09:00" --ultimate-goal "Improve knee mobility and reduce pain" --exercise-routine "backend/update_information/sample_exercise_routine.json"
```

## Testing the schedule_notification Function

The `schedule_notification` function schedules notifications for patients.

### Basic Usage

```bash
python backend/schedule_notification/test_function.py --base-url "http://localhost:8080" --patient-id "user123"
```

This will schedule a notification for 5 minutes from now.

### Schedule for Specific Time

```bash
python backend/schedule_notification/test_function.py --base-url "http://localhost:8080" --patient-id "user123" --scheduled-time "2023-04-15T10:00:00Z"
```

### Schedule Exercise Reminder

```bash
python backend/schedule_notification/test_function.py --base-url "http://localhost:8080" --patient-id "user123" --notification-type "exercise_reminder" --exercise-id "exercise123"
```

## Testing the update_fcm_token Function

The `update_fcm_token` function updates a patient's Firebase Cloud Messaging token.

### Basic Usage

```bash
python backend/schedule_notification/test_update_fcm_token.py --base-url "http://localhost:8080" --patient-id "user123" --fcm-token "fcm_token_here"
```

## Testing with Deployed Functions

To test with deployed functions, replace the base URL with the deployed function URL:

```bash
python backend/update_information/test_function.py --base-url "https://us-central1-pepmvp.cloudfunctions.net" --patient-id "user123" --notification-time "09:00"
```

```bash
python backend/schedule_notification/test_function.py --base-url "https://us-central1-pepmvp.cloudfunctions.net" --patient-id "user123" --scheduled-time "2023-04-15T10:00:00Z"
```

```bash
python backend/schedule_notification/test_update_fcm_token.py --base-url "https://us-central1-pepmvp.cloudfunctions.net" --patient-id "user123" --fcm-token "fcm_token_here"
```

## Local Development

To test locally, you need to run the functions locally using the Firebase Emulator:

```bash
firebase emulators:start
```

Then use the local URLs in your test commands:

```bash
python backend/update_information/test_function.py --base-url "http://localhost:5001/pepmvp/us-central1" --patient-id "user123" --notification-time "09:00"
```

## Troubleshooting

If you encounter issues with the test tools:

1. Make sure the cloud functions are running (either locally or deployed)
2. Check that the patient ID exists in your Firestore database
3. Verify that the request format matches the expected format for each function
4. Check the function logs for any errors 