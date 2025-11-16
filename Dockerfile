FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY organize_series.py .
COPY templates/ templates/

# Create directories for volumes
RUN mkdir -p /app/tv /app/tv_unordered

# Expose port
EXPOSE 9002

# Run the application
CMD ["python", "app.py"]
