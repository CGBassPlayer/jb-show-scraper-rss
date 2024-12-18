FROM python:3.11-alpine

ENV PIPENV_VENV_IN_PROJECT=1
RUN pip install pipenv
ENTRYPOINT [ "pipenv", "run" ]
CMD [ "scraper" ]

WORKDIR /scraper
COPY Pipfile .
COPY Pipfile.lock .
RUN pipenv sync
COPY ./models/ ./models/
COPY scraper.py config.yml ./
RUN mkdir -p /data && chown -R 1000:1000 ./scraper.py .venv/ /data

USER 1000