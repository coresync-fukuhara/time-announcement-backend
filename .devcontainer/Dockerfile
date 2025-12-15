FROM python:3.13

RUN pip install --upgrade pip setuptools wheel
RUN apt update
RUN apt install -y pkg-config python3-dev build-essential libgirepository1.0-dev portaudio19-dev pulseaudio

WORKDIR /app