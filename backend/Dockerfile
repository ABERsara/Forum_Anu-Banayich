FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer stays cached across builds
# unless pyproject.toml actually changes.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
