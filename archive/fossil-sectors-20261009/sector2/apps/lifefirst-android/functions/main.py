# Import the necessary Firebase Admin SDK components
from firebase_functions import https_fn
from firebase_admin import initialize_app

# Initialize Firebase Admin SDK (required for interacting with Firebase services)
# This is typically done once per function instance.
initialize_app()

@https_fn.on_request()
def helloWorld(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function that responds with 'Hello from Firebase!'
    """
    # This function is triggered by an HTTP request.
    # The 'request' object contains details about the incoming HTTP request.

    # We'll just return a simple text response.
    return https_fn.Response("Hello from Firebase! Your Python Cloud Function is working.", mimetype="text/plain")

