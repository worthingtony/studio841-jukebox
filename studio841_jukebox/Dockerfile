FROM python:3.12-alpine

LABEL \
    io.hass.version="0.1.0" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jukebox/ /app/jukebox/

# Options are read from /data/options.json. Nothing here prints them - they will hold
# credentials once the Network Control fallback is wired in.
CMD ["python3", "-u", "-m", "jukebox.main"]
