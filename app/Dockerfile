# Small, recent Python image
FROM python:3.12-slim

# Do not buffer Python output (good for logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install OS deps (if any) then Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .

# Expose the app port
EXPOSE 8000

# Simple command (Flask dev server is ok for lab)
CMD ["python", "app.py"]
# For production-like serving, consider:
# CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
