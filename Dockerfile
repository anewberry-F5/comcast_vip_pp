# Use official Python 3.12 slim image
FROM python:3.12-slim

# Install system dependencies (curl for healthchecks & CLI curl mode, netcat for TCP/UDP probes, ca-certificates for HTTPS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-openbsd \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Install Python dependencies into system environment
RUN uv pip install --system .

# Copy application source code
COPY . /app

# Expose Streamlit default port
EXPOSE 8501

# Healthcheck for Streamlit container
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Launch Streamlit app
ENTRYPOINT ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
