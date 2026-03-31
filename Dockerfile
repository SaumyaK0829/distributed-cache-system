# Use official Python image as base
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app code
COPY . .

# Expose port 8000 (where FastAPI runs)
EXPOSE 8000

# Command to run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# What's happening here:

# FROM python:3.11-slim — slim version means smaller image size, faster deploys
# COPY requirements.txt . before COPY . . — this is a Docker layer caching trick. Dependencies only reinstall when requirements.txt changes, not every time your code changes. Saves a ton of build time.
# --host 0.0.0.0 — makes the app accessible outside the container (not just localhost)
# --reload — auto-restarts when code changes, great for development

