# Quiz Backend

Backend for the Avanti Quiz Engine created using FastAPI and MongoDB!

## Installation

- Create a virtual environment (make sure that `virtualenv` is installed on your system):

```bash
virtualenv venv
```

- Activate the environment:

```bash
source venv/bin/activate
```

- Install the dependencies:

```bash
pip install -r app/requirements.txt
```

- Install `pre-commit`

```
pip install pre-commit
```

- Set up `pre-commit`

```
pre-commit install
```

## Running locally

Simply run:

```
cd app; uvicorn main:app --reload
```

You should see a message like:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [98098] using watchgod
INFO:     Started server process [98100]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     127.0.0.1:58550 - "GET /docs HTTP/1.1" 200 OK
INFO:     127.0.0.1:58550 - "GET /openapi.json HTTP/1.1" 200 OK
```

Use `http://127.0.0.1:8000` as the base URL of the endpoints and navigate to `http://127.0.0.1:8000/docs` to see the auto-generated docs! :dancer:

## Deployment

- Install [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)

- Install Docker and start Docker.

### Staging

- Create the deployment stack (only required for the first time):

```bash
sam deploy --stack-name QuizBackendStaging --s3-bucket quiz-staging-backend --capabilities CAPABILITY_IAM -t templates/staging.yaml
```

If the deployment was successful, you should see a message as shown in the image below:
![deployment successful](images/deployment-succeeded.png)

The app will be deployed on the URL corresponding to `Value` in the image above!

- Once the stack has been deployed, subsequent changes to the code can be uploaded to the lambda function by running:

```bash
sam sync --stack-name QuizBackendStaging -t templates/staging.yaml
```

- If you want your files to automatically be synced to your deployment, simply add `--watch` at the end of the previous command.

```
sam sync --stack-name QuizBackendStaging -t templates/staging.yaml --watch
```

### Production

The steps are similar to that in Staging.

- Create the deployment stack (only required for the first time):

```
sam deploy --stack-name QuizBackendProd --s3-bucket quiz-prod-backend --capabilities CAPABILITY_IAM -t templates/prod.yaml
```

- Once the stack has been deployed, subsequent changes to the code can be uploaded to the lambda function by running:

```
sam sync --stack-name QuizBackendProd -t templates/prod.yaml
```

- If you want your files to automatically be synced to your deployment, simply add `--watch` at the end of the previous command.

```
sam sync --stack-name QuizBackendProd -t templates/prod.yaml --watch
```

## Tests

### Installation

- Install mongoengine

```
python -m pip install mongoengine
```

- Install pytest

```
pip install -U pytest
```

### Testing

- Run command

```
py -m pytest app/tests/questions.py
```
