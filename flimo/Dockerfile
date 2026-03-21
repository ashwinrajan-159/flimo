# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (if any are needed for libraries like numpy/faiss)
# faiss-cpu usually has wheels, so system deps might be minimal.
# But sometimes build-essential is needed. Keeping it slim for now.

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY src/ src/
# Note: we don't copy data/ or logs/ as those should be volumes
# But we might want to copy config files if they exist outside src

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
