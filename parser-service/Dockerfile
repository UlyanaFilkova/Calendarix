# Base Python image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Working directory inside the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy parser source code
COPY . .

# Start the parser worker
CMD ["python", "main.py"]
