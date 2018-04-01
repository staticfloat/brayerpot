FROM python:3

RUN mkdir -p /app
WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt && \
    rm -f requirements.txt

# Embed secret args
ARG SLACK_API_TOKEN
RUN echo "SLACK_API_TOKEN=\"${SLACK_API_TOKEN}\"" >> secret.py

# Set the proper timezone
ENV TZ=America/Los_Angeles
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY brayerpot.py ./brayerpot.py
CMD ["python", "brayerpot.py"]
STOPSIGNAL INT