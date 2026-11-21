FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

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

# Run as an unprivileged user: the server only reads its code and templates.
RUN useradd --system --uid 10001 --no-create-home awth
USER awth

CMD ["python", "app.py"]
