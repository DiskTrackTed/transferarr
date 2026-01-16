"""
Validation decorator for API routes.

This module provides the @validate_json decorator that validates
incoming request JSON against a marshmallow schema before the
route handler executes.
"""
from functools import wraps
from flask import request
from marshmallow import ValidationError
from .responses import error_response


def validate_json(schema_class):
    """Decorator to validate request JSON against a marshmallow schema.
    
    Usage:
        @bp.route("/endpoint", methods=["POST"])
        @validate_json(MySchema)
        def my_handler():
            data = request.validated_data  # Already validated and deserialized
            ...
    
    Args:
        schema_class: A marshmallow Schema class to validate against
        
    Returns:
        Decorated function that validates JSON before executing
        
    On validation failure:
        Returns 400 error response with VALIDATION_ERROR code and
        detailed error messages in the details field.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            schema = schema_class()
            try:
                # Load and validate the request JSON
                # schema.load() returns deserialized data and raises ValidationError on failure
                data = schema.load(request.json or {})
                # Attach validated data to request for handler to use
                request.validated_data = data
            except ValidationError as err:
                # Return standardized error response with field-level details
                return error_response(
                    code="VALIDATION_ERROR",
                    message="Invalid request data",
                    details=err.messages,
                    status_code=400
                )
            return f(*args, **kwargs)
        return decorated_function
    return decorator
