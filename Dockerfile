# Use a lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app source code
COPY . .

# Copy preexisting LUTs into the container
COPY luts/ /app/luts/

# Ensure LUT folder exists (for any future LUTs)
RUN mkdir -p /app/luts

# Expose port for the webapp
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=development

# Start Flask
CMD ["flask", "run"]
