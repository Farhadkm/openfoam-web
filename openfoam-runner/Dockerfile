FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV JOBS_ROOT=/jobs
ENV OPENFOAM_IMAGE=opencfd/openfoam-run:2512
ENV OPENFOAM_BASHRC=/usr/lib/openfoam/openfoam2512/etc/bashrc
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
