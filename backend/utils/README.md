# Structured Logging Framework for PEP MVP

This directory contains utilities for implementing a standardized, structured logging system across all backend services.

## Benefits

- **Consistent Format**: All logs follow the same JSON structure for easier parsing
- **Correlation IDs**: Track request flows across multiple services
- **User Context**: Associate logs with specific users for easier troubleshooting
- **Automatic Metadata**: Captures code location, timestamp, and execution context
- **Sanitization**: Automatically redacts sensitive information
- **Activity Tracking**: Records important user activities for analytics

## Files

- `logging_utils.py`: Core logging library
- `logging_update_tool.py`: Utility to update existing code to use structured logging
- `logging_dashboard.json`: GCP Monitoring dashboard configuration

## Quick Usage

```python
# Import the logging utilities
from utils.logging_utils import create_logger, log_function_call, log_user_activity

# Create a logger for your service
log = create_logger('my_service_name')

# Decorate your Cloud Function
@functions_framework.http
@log_function_call(log)
def my_function(request):
    # Set user context if available
    user_id = request.get_json().get('user_id')
    log.set_context(user_id=user_id)
    
    # Simple logging
    log.info("Processing request")
    
    # Structured logging with data
    log.info("User data retrieved", {
        "user_id": user_id,
        "has_profile": user_has_profile
    })
    
    # Error logging
    try:
        # Some operation
        pass
    except Exception as e:
        log.error("Operation failed", {
            "error": str(e)
        }, exc_info=True)
    
    # Track user activity
    log_user_activity(user_id, "completed_exercise", {
        "exercise_id": exercise_id,
        "duration_minutes": 10
    })
```

## Installation

1. Copy the `utils` directory to your project root
2. Update your deployment script to include the utils directory

## Converting Existing Functions

Use the conversion tool to update existing Cloud Functions:

```bash
cd backend/utils
python logging_update_tool.py ../send_notification
```

After automatic conversion, manually check the results and update any complex logging patterns that weren't converted correctly.

## Log Format

All logs follow this JSON structure:

```json
{
  "timestamp": "2025-05-05T00:05:39.513254Z",
  "service": "send_notification",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "3bad2322-2b91-4f06-8e87-e2c06a090e35",
  "location": "main.py:send_notification",
  "message": "Processing notification request",
  "data": {
    "notification_id": "9b515ec6-3f27-4589-8c18-caa252cb90ab"
  }
}
```

## Dashboard Setup

1. Go to Google Cloud Console > Monitoring > Dashboards
2. Click "Create Dashboard"
3. Click "JSON Editor" 
4. Paste the contents of `logging_dashboard.json`
5. Click "Save"

## Best Practices

1. **Use structured logging for all data**:
   ```python
   # Don't do this:
   log.info(f"Retrieved {len(results)} results for user {user_id}")
   
   # Do this instead:
   log.info("Retrieved results", {
     "user_id": user_id,
     "result_count": len(results)
   })
   ```

2. **Add request context**: Set user_id and request_id when available

3. **Use appropriate log levels**:
   - `debug`: Detailed information for debugging
   - `info`: Confirmation that things are working
   - `warning`: Something unexpected but not an error
   - `error`: Something failed but the application continues
   - `critical`: Application failure requiring immediate attention

4. **Log activities consistently**: Use `log_user_activity` for all significant user actions

5. **Include actionable data**: Make sure logs contain enough information to understand what happened

## Querying Logs

### Basic Log Query

```
resource.type="cloud_function"
resource.labels.function_name="send_notification"
```

### Advanced Queries

Find errors for a specific user:
```
resource.type="cloud_function"
severity>=ERROR
jsonPayload.user_id="3bad2322-2b91-4f06-8e87-e2c06a090e35"
```

Track request across services:
```
resource.type="cloud_function"
jsonPayload.request_id="550e8400-e29b-41d4-a716-446655440000"
```

Monitor specific activities:
```
resource.type="cloud_function"
jsonPayload.activity_type="notification_sent"
``` 