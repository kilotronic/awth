FROM python:3.13-slim

WORKDIR /app

# Install the awth package with server (Flask) dependency
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir ".[server]"

# Copy the Flask app and templates
COPY app.py .
COPY templates/ templates/

# Bind all interfaces inside the container: the container boundary + published
# ports are the exposure control here, and loopback would make the published
# port unreachable. On the host, the default (loopback) still applies.
ENV AWTH_HOST=0.0.0.0

EXPOSE 4999

CMD ["python", "app.py"]
