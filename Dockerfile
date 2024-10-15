FROM python:3.11.9-alpine3.20
WORKDIR /usr/src/app

COPY . .

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5678

ENTRYPOINT [ "python", "manage.py", "runserver", "0.0.0.0:5678"]

