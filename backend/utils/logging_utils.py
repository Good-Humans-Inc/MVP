import json
import logging
import uuid
import inspect
import os
from datetime import datetime
from functools import wraps
from google.cloud import logging as cloud_logging

# Configure the standard logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('pep-mvp')

# Initialize GCP Cloud Logging
try:
    client = cloud_logging.Client()
    client.setup_logging(log_level=logging.INFO)
    GCP_ENABLED = True
except Exception:
    GCP_ENABLED = False
    logger.warning("GCP Cloud Logging could not be initialized. Using standard logging.")

def generate_request_id():
    """Generate a unique request ID for tracing."""
    return str(uuid.uuid4())

class StructuredLogger:
    """Structured logger that formats logs consistently."""
    
    def __init__(self, service_name):
        self.service_name = service_name
        self.request_id = None
        self.user_id = None
    
    def set_context(self, request_id=None, user_id=None):
        """Set the current request context."""
        self.request_id = request_id or generate_request_id()
        self.user_id = user_id
        return self
    
    def _format_log(self, message, additional_data=None):
        """Format log message as structured data."""
        caller_frame = inspect.currentframe().f_back.f_back
        function_name = caller_frame.f_code.co_name
        file_name = os.path.basename(caller_frame.f_code.co_filename)
        
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service": self.service_name,
            "request_id": self.request_id,
            "location": f"{file_name}:{function_name}",
            "message": message
        }
        
        if self.user_id:
            log_data["user_id"] = self.user_id
            
        if additional_data:
            # Sanitize additional data to remove sensitive info
            sanitized_data = self._sanitize_data(additional_data)
            log_data["data"] = sanitized_data
            
        return log_data
    
    def _sanitize_data(self, data):
        """Remove sensitive fields from data before logging."""
        if not isinstance(data, dict):
            return data
            
        sensitive_fields = ['password', 'token', 'key', 'secret', 'auth', 'fcm_token']
        sanitized = {}
        
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_data(value)
            else:
                sanitized[key] = value
                
        return sanitized
    
    def debug(self, message, data=None):
        """Log a debug message."""
        log_data = self._format_log(message, data)
        logger.debug(json.dumps(log_data))
        return log_data
    
    def info(self, message, data=None):
        """Log an info message."""
        log_data = self._format_log(message, data)
        logger.info(json.dumps(log_data))
        return log_data
    
    def warning(self, message, data=None):
        """Log a warning message."""
        log_data = self._format_log(message, data)
        logger.warning(json.dumps(log_data))
        return log_data
    
    def error(self, message, data=None, exc_info=None):
        """Log an error message."""
        log_data = self._format_log(message, data)
        logger.error(json.dumps(log_data), exc_info=exc_info)
        return log_data
    
    def critical(self, message, data=None, exc_info=None):
        """Log a critical message."""
        log_data = self._format_log(message, data)
        logger.critical(json.dumps(log_data), exc_info=exc_info)
        return log_data

def create_logger(service_name):
    """Create a structured logger for a service."""
    return StructuredLogger(service_name)

def log_function_call(logger):
    """Decorator to log function entries and exits."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Log function entry
            request_id = generate_request_id()
            
            # Try to extract user_id from arguments
            user_id = None
            if args and len(args) > 0 and hasattr(args[0], 'get_json'):
                try:
                    request_json = args[0].get_json()
                    if request_json and 'user_id' in request_json:
                        user_id = request_json.get('user_id')
                except Exception:
                    pass
            
            logger.set_context(request_id=request_id, user_id=user_id)
            
            # Sanitize args and kwargs for logging
            safe_args = [arg if isinstance(arg, (int, float, str, bool)) else type(arg).__name__ for arg in args]
            safe_kwargs = {k: v if isinstance(v, (int, float, str, bool)) else type(v).__name__ for k, v in kwargs.items()}
            
            logger.info(f"Function {func.__name__} called", {
                "args": safe_args,
                "kwargs": safe_kwargs
            })
            
            try:
                # Execute the function
                result = func(*args, **kwargs)
                
                # Log function success
                if isinstance(result, tuple) and len(result) >= 2 and isinstance(result[1], int):
                    status_code = result[1]
                    status_text = "success" if 200 <= status_code < 300 else "error"
                    logger.info(f"Function {func.__name__} completed with status {status_code}", {
                        "status": status_text,
                        "status_code": status_code
                    })
                else:
                    logger.info(f"Function {func.__name__} completed successfully")
                
                return result
                
            except Exception as e:
                # Log function error
                logger.error(f"Function {func.__name__} failed: {str(e)}", exc_info=True)
                raise
        
        return wrapper
    return decorator

# User activity logging
def log_user_activity(user_id, activity_type, details=None):
    """Log user activity for analytics and monitoring."""
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "activity_type": activity_type
    }
    
    if details:
        log_data["details"] = details
    
    # Save to Firestore and log the activity
    try:
        from firebase_admin import firestore
        db = firestore.Client(project='pepmvp', database='pep-mvp')
        
        # Save to user_activities collection
        db.collection('user_activities').add({
            **log_data,
            "created_at": firestore.SERVER_TIMESTAMP
        })
        
        # Log to Cloud Logging as well
        logger.info(f"User activity: {activity_type}", log_data)
        
    except Exception as e:
        logger.error(f"Failed to log user activity: {str(e)}", {
            "user_id": user_id,
            "activity_type": activity_type
        }) 