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
# We'll use port 8000, which is common for Gunicorn
EXPOSE 8000

# Define environment variables for the Flask app
# These should match what's in your .env file or be provided during 'docker run'
ENV FLASK_APP=app.py
ENV FLASK_DEBUG=1 # Set to 0 for production, 1 for development (inside container)

# Define variables for Arkesel API if not in .env or for default values
# These are examples; adjust based on your actual .env or desired defaults
ENV FLASK_SECRET_KEY='f2729120bffc2cb1178ccfcea65823f8864328c46e63d247'
ENV APP_ADMIN_USERNAME='admin'
ENV APP_ADMIN_PASSWORD='password123'
ENV APP_SALES_USERNAME='sales'
ENV APP_SALES_PASSWORD='password123'
ENV ARKESEL_API_KEY='b0FrYkNNVlZGSmdrendVT3hwUHk'
ENV ARKESEL_SENDER_ID='Uniquebence'
ENV ADMIN_PHONE_NUMBER='233547096268'
ENV ENTERPRISE_NAME='My Pharmacy'
ENV PHARMACY_LOCATION='Accra, Ghana'
ENV PHARMACY_ADDRESS='123 Main St, City'
ENV PHARMACY_CONTACT='+233547096268'

# Run Gunicorn to serve the Flask application
# 0.0.0.0 makes the app accessible from outside the container
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:8000"]
