"""
Standard response helpers for API endpoints.

All API responses follow the minimal envelope format:
- Success: {"data": ..., "message": "..."}
- Error: {"error": {"code": "...", "message": "...", "details": {...}}}

This provides consistent structure for frontend parsing and error handling.
"""
from flask import jsonify


def success_response(data=None, message=None, status_code=200):
    """Standard success response format.
    
    Args:
        data: The response data (can be dict, list, or None)
        message: Optional success message
        status_code: HTTP status code (default 200)
    
    Returns:
        tuple: (Flask response, status_code)
    """
    response = {"data": data}
    if message:
        response["message"] = message
    return jsonify(response), status_code


def error_response(code, message, details=None, status_code=400):
    """Standard error response format.
    
    Args:
        code: Error code (e.g., "VALIDATION_ERROR", "NOT_FOUND")
        message: Human-readable error message
        details: Optional dict with additional error details
        status_code: HTTP status code (default 400)
    
    Returns:
        tuple: (Flask response, status_code)
    """
    response = {
        "error": {
            "code": code,
            "message": message
        }
    }
    if details:
        response["error"]["details"] = details
    return jsonify(response), status_code


def created_response(data, message=None):
    """Response for successful creation (201 Created).
    
    Args:
        data: The created resource data
        message: Optional success message
    
    Returns:
        tuple: (Flask response, 201)
    """
    return success_response(data, message, 201)


def not_found_response(resource_type, identifier):
    """Standard 404 Not Found response.
    
    Args:
        resource_type: Type of resource (e.g., "Client", "Connection")
        identifier: The identifier that was not found
    
    Returns:
        tuple: (Flask response, 404)
    """
    return error_response(
        f"{resource_type.upper()}_NOT_FOUND",
        f"{resource_type} '{identifier}' not found",
        status_code=404
    )


def validation_error_response(message, details=None):
    """Standard 400 validation error response.
    
    Args:
        message: Human-readable validation error message
        details: Optional dict with field-specific errors
    
    Returns:
        tuple: (Flask response, 400)
    """
    return error_response("VALIDATION_ERROR", message, details, status_code=400)


def server_error_response(message):
    """Standard 500 server error response.
    
    Args:
        message: Human-readable error message
    
    Returns:
        tuple: (Flask response, 500)
    """
    return error_response("SERVER_ERROR", message, status_code=500)
