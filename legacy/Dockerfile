# Use the official Python image from the Docker Hub
FROM ubuntu
FROM python:latest

# These two environment variables prevent __pycache__/ files.
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# Update aptitude with new repo
RUN apt-get update

# Install software
RUN apt-get install -y git

ENV GIT_ACCESS_TOKEN=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

# Copy Git Code.
RUN git clone https://abhisheksahu92:${GIT_ACCESS_TOKEN}@github.com/abhisheksahu92/Interview-Portal

# Upgrade pip
RUN pip install --upgrade pip

# Install the requirements.
RUN pip install -r Interview-Portal/requirements.txt