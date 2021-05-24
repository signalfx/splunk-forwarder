FROM python:3.8

RUN curl -fsSL get.docker.com -o /tmp/get-docker.sh && \
    sh /tmp/get-docker.sh

COPY ./ /code
WORKDIR /code

RUN pip install -r /code/tests/requirements.txt

CMD pytest -n auto --verbose tests/splunk_test.py
