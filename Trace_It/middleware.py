import traceback
import logging
from django.http import HttpResponse

logger = logging.getLogger('django')

class ErrorLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        error_msg = f"""
========== ERROR ==========
URL: {request.path}
Method: {request.method}
User: {request.user}
Exception: {str(exception)}
Traceback:
{traceback.format_exc()}
===========================
"""
        logger.error(error_msg)
        # Also write to a separate file for easy access
        with open('error_details.log', 'a') as f:
            f.write(error_msg)
        return None