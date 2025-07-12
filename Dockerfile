# Use an official Python runtime as a parent image
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir speeds up the installation by not storing build cache
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Expose the port that Gunicorn will listen on
EXPOSE 8000

# Define environment variables for the Flask app
ENV FLASK_APP=app.py
ENV FLASK_DEBUG=0 # Set to 0 for production, 1 for development (inside container)

# Define variables for Arkesel API if not in .env or for default values
# These are examples; adjust based on your actual .env or desired defaults
ENV FLASK_SECRET_KEY='your_super_secret_key_here'
ENV SUPER_ADMIN_USERNAME='superadmin' # Added for clarity in Dockerfile
ENV SUPER_ADMIN_PASSWORD='superpassword' # Added for clarity in Dockerfile
ENV APP_ADMIN_USERNAME='admin' # This is a placeholder, users are now in DB
ENV APP_ADMIN_PASSWORD='password123' # This is a placeholder, users are now in DB
ENV APP_SALES_USERNAME='sales' # This is a placeholder, users are now in DB
ENV APP_SALES_PASSWORD='password123' # This is a placeholder, users are now in DB
ENV ARKESEL_API_KEY='b0FrYkNNVlZGSmdrendVT3hwUHk'
ENV ARKESEL_SENDER_ID='PHARMACY'
ENV ADMIN_PHONE_NUMBER='233543169389'
ENV ENTERPRISE_NAME='My Pharmacy'
ENV PHARMACY_LOCATION='Accra, Ghana'
ENV PHARMACY_ADDRESS='123 Main St, City'
ENV PHARMACY_CONTACT='+233543169389'

# Note: DATABASE_URL will be provided by Render's environment variables directly,
# so it's not set here. For local development, ensure it's in your local .env

# Run Gunicorn to serve the Flask application
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000"]
