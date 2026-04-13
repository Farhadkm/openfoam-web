FROM kitware/trame:conda-2025-09

# VTK needs a software OpenGL backend for headless scene serialization
# (VtkLocalView still renders in the browser, but the server must walk the
# VTK pipeline which internally requires an initialised render window).
USER root
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends libosmesa6 \
 && rm -rf /var/lib/apt/lists/*
USER trame-user

WORKDIR /deploy
COPY --chown=trame-user:trame-user requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=trame-user:trame-user app.py ./app.py

ENV JOBS_ROOT=/jobs
EXPOSE 8090

# kitware/trame images expect to be launched via their entrypoint.
# Use the standard `trame` launcher and point to our app.
CMD ["trame", "run", "--server", "/deploy/app.py", "--host", "0.0.0.0", "--port", "8090"]

