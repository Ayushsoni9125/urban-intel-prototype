FROM python:3.11-slim

# Install system dependencies
# - Node.js for building the React frontend
# - OpenCV dependencies (libgl1, libglib2.0-0)
RUN apt-get update && apt-get install -y curl \
    libgl1 libglib2.0-0 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user (Hugging Face Spaces requirement)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Install Python dependencies first (leverage Docker caching)
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files with proper permissions
COPY --chown=user . .

# Build the React frontend
WORKDIR /app/dashboard
RUN npm install
RUN npm run build

# Switch back to app root
WORKDIR /app

# Ensure output directories exist for YOLO to write to
RUN mkdir -p detection/output/alerts

# Expose port 7860 (Hugging Face Spaces default)
EXPOSE 7860

# Start FastAPI server on port 7860
CMD ["uvicorn", "detection.server:app", "--host", "0.0.0.0", "--port", "7860"]
