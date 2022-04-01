# Quiz Backend

Backend for the Avanti Quiz Engine created using FastAPI and MongoDB!

## Installation

- Install [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)

- Install Docker and start Docker.

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
sam local start-api
```

Once the docker image has completed building, you can use `http://127.0.0.1:3000` as the base URL of the endpoints and navigate to `http://127.0.0.1:3000/docs` to see the auto-generated docs! :dancer:

## Deployment

### Staging

Run:

```
sam deploy --stack-name QuizBackendStaging --s3-bucket quiz-backend-staging --capabilities CAPABILITY_IAM
```

If the deployment was successful, you should see a message as shown in the image below:
![deployment successful](images/deployment-succeeded.png)

The app will be deployed on the URL corresponding to `Value` in the image above!

### Production

Similar to Staging, simply run:

```
sam deploy --stack-name QuizBackendProd --s3-bucket quiz-backend-prod --capabilities CAPABILITY_IAM
```
