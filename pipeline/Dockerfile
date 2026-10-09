FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pipeline/requirements.txt pipeline-requirements.txt
RUN pip install --no-cache-dir -r pipeline-requirements.txt

COPY pipeline ./pipeline

ENTRYPOINT ["python", "-m", "pipeline"]
CMD ["status"]
