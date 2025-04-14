# Quiz Backend


[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![codecov](https://codecov.io/gh/avantifellows/quiz-backend/branch/main/graph/badge.svg)](https://codecov.io/gh/avantifellows/quiz-backend)
[![Discord](https://img.shields.io/discord/717975833226248303.svg?label=&logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2&style=flat-square)](https://discord.gg/29qYD7fZtZ)

The backend for a generic mobile-friendly quiz engine created using FastAPI and MongoDB! The frontend can be found [here](https://github.com/avantifellows/quiz-frontend).

## Table of Contents:

  * [Installation](#installation)
    + [Local DB Setup](#local-db-setup)
      - [Linux Systems](#linux-systems)
      - [Mac Systems](#mac-systems)
    + [Virtual Environment Setup](#virtual-environment-setup)
  * [Running locally](#running-locally)
    + [How to pull the latest data from Prod / Staging DB to your local DB before you start working on a feature?](#how-to-pull-the-latest-data-from-prod---staging-db-to-your-local-db-before-you-start-working-on-a-feature-)
      - [What's happening above?](#what-s-happening-above-)
  * [Deployment](#deployment)
  * [Tests](#tests)

## Installation

### Local DB Setup

#### Linux Systems
The following steps are for a Linux system.
- To run the backend locally, you would need to setup a local instance of mongodb. The offical instructions [here](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-ubuntu/) are good and simple enough to follow. Those steps are also listed down below.

  - Import the public key used by the package management system.
  Issue the following command to import the MongoDB public GPG Key from [here](https://pgp.mongodb.com/server-6.0.asc):
    ```
    curl -fsSL https://pgp.mongodb.com/server-6.0.asc | \
    sudo gpg -o /usr/share/keyrings/mongodb-server-6.0.gpg \
    --dearmor
    ```

  - From a terminal, install gnupg if it is not already available:
    ```
    sudo apt-get install gnupg
    ```
  - Create a list file for MongoDB.
    Create the list file `/etc/apt/sources.list.d/mongodb-org-6.0.list` for your version of Ubuntu. To check the Ubuntu version the host is running, open a terminal or shell on the host and execute
    ```
    lsb_release -dc
    ```

    According to the version, run the respective code on the terminal. The below code is for the Ubuntu version 22.04(Jammy), if you have a different version running then replace the the below command according to your version from [here](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-ubuntu/#create-a-list-file-for-mongodb).

      - Ubuntu 22.04 (Jammy)
        ```
        echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
        ```

  - Reload local package database.
    Issue the following command to reload the local package database:
    ```
    sudo apt-get update
    ```
  - Install the MongoDB packages
    Install the latest stable version of MongoDB
    ```
    sudo apt-get install -y mongodb-org
    ```


#### Mac Systems
The following steps are for a Mac system.
- To run the backend locally, you would need to setup a local instance of mongodb. The offical instructions [here](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-os-x/#run-mongodb-community-edition) are good and simple enough to follow. Those steps are also listed down below.

  - Install the Xcode command-line tools
    ```bash
    xcode-select --install
    ```
  - Make sure you have homebrew installed. If not, go [here](https://brew.sh/#install)
  - Download the official Homebrew formula for MongoDB
    ```bash
    brew tap mongodb/brew
    ```
  - Update Homebrew and all existing formulae
    ```bash
    brew update
    ```
  - Install MongoDB
    ```bash
    brew install mongodb-community@6.0
    ```
  - Make sure mongosh (your mongo shell) is added to the PATH. To test it out, type `mongosh` in your terminal and press enter. It should NOT give any error.

### Virtual Environment Setup

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

- Install `pre-commit`:
  ```
  pip install pre-commit
  ```

- Set up `pre-commit`:
  ```
  pre-commit install
  ```

- Copy `.env.example` to `.env` and set all the environment variables as mentioned in `docs/ENV.md`. No need to change anything if you're planning to connect to a local DB. If you're planning to connect your local server to a staging and prod DB, only then you need to change. PLEASE DO NOT CONNECT YOUR LOCAL INSTANCE TO STAGING/PROD DB.

## Running locally
For Linux machines, simply run the below in the terminal:
```bash
chmod +x startServerLinux.sh
./startServerLinux.sh
```
For Mac Simply run:

```bash
chmod +x startServerMac.sh
./startServerMac.sh
```

You should see a message like:
```bash
Starting the mongod process
Service `mongodb-community` already started, use `brew services restart mongodb-community` to restart.
Starting the server now
INFO:     Will watch for changes in these directories: ['/Users/deepansh/Documents/Work/repos/quiz-backend/app']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [38899] using statreload
INFO:     Started server process [38901]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Use `http://127.0.0.1:8000` as the base URL of the endpoints and navigate to `http://127.0.0.1:8000/docs` to see the auto-generated docs! :dancer:

### How to pull the latest data from Prod / Staging DB to your local DB before you start working on a feature?


You can pass arguments to the `startServerMac` script.
- `--freshSync` : Passing this argument means you're telling the script to take a fresh sync from the cloud DB to your local DB. By default, this is false.
- `--source` : When `--freshSync` is specified, a source is also needed. Whether you need to sync from prod db or staging db. Please specify the full [mongo URI](https://www.mongodb.com/docs/manual/reference/connection-string/) of the DB you want to take a sync from. Note: Currently it might take 10-15 minutes for the sync process to be done. We're working on improving this.

Example:
```bash
./startServerMac.sh --freshSync --source mongodb+srv://quiz:<YOUR-PASSWORD>@quiz-staging-m10.uocfg.mongodb.net/quiz
```

You should see a message like:
```bash
Starting the mongod process
Service `mongodb-community` already started, use `brew services restart mongodb-community` to restart.
Fresh sync is true -- Going to remove current db and take a fresh sync


Removing the existing data in the local database
Current Mongosh Log ID:	642317a1139325e074af0309
Connecting to:		mongodb://127.0.0.1:27017/?directConnection=true&serverSelectionTimeoutMS=2000&appName=mongosh+1.8.0
Using MongoDB:		6.0.5
Using Mongosh:		1.8.0

For mongosh info see: https://docs.mongodb.com/mongodb-shell/

------
   The server generated these startup warnings when booting
   2023-03-27T15:17:54.237+05:30: Access control is not enabled for the database. Read and write access to data and configuration is unrestricted
   2023-03-27T15:17:54.237+05:30: Soft rlimits for open file descriptors too low
------

------
   Enable MongoDB's free cloud-based monitoring service, which will then receive and display
   metrics about your deployment (disk utilization, CPU, operation statistics, etc).

   The monitoring data will be available on a MongoDB website with a unique URL accessible to you
   and anyone you share the URL with. MongoDB may use this information to make product
   improvements and to suggest MongoDB products and deployment options to you.

   To enable free monitoring, run the following command: db.enableFreeMonitoring()
   To permanently disable this reminder, run the following command: db.disableFreeMonitoring()
------

{ ok: 1, dropped: 'quiz' }
quiz DB dropped



Taking a fresh sync from staging DB:


Downlading the data from staging DB
2023-03-28T22:06:51.043+0530	WARNING: On some systems, a password provided directly in a connection string or using --uri may be visible to system status programs such as `ps` that may be invoked by other users. Consider omitting the password to provide it via stdin, or using the --config option to specify a configuration file with the password.
2023-03-28T22:06:52.228+0530	writing quiz.quizzes to dump/quiz/quizzes.bson
2023-03-28T22:06:52.264+0530	writing quiz.session_answers to dump/quiz/session_answers.bson
2023-03-28T22:06:52.300+0530	writing quiz.sessions to dump/quiz/sessions.bson
2023-03-28T22:06:52.377+0530	writing quiz.questions to dump/quiz/questions.bson
2023-03-28T22:06:54.063+0530	[###.....................]          quiz.quizzes      101/611  (16.5%)
2023-03-28T22:06:54.064+0530	[........................]  quiz.session_answers  101/7868281   (0.0%)
2023-03-28T22:06:54.064+0530	[........................]         quiz.sessions   101/121840   (0.1%)
2023-03-28T22:06:54.064+0530	[........................]        quiz.questions    101/18467   (0.5%)

Data downloaded from staging DB, restoring the data in local DB
2023-03-28T22:40:05.949+0530	using default 'dump' directory
2023-03-28T22:40:05.951+0530	preparing collections to restore from
2023-03-28T22:40:06.034+0530	reading metadata for quiz.organization from dump/quiz/organization.metadata.json
2023-03-28T22:40:06.038+0530	reading metadata for quiz.questions from dump/quiz/questions.metadata.json
2023-03-28T22:40:06.038+0530	reading metadata for quiz.quizzes from dump/quiz/quizzes.metadata.json
2023-03-28T22:40:06.038+0530	reading metadata for quiz.session_answers from dump/quiz/session_answers.metadata.json
2023-03-28T22:40:06.039+0530	reading metadata for quiz.sessions from dump/quiz/sessions.metadata.json

Removing the downloaded dump folder
Starting the server now
INFO:     Will watch for changes in these directories: ['/Users/deepansh/Documents/Work/repos/quiz-backend/app']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [37464] using statreload
INFO:     Started server process [37466]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```


#### What's happening above?
- mongo service is started using homebrew if not already started
- existing db is cleared
- a data dump from staging/prod db is taken
- the downloaded data is restored to the local db
- the downloaded dump is deleted
- virtual environment is started up and uvicorn app is started

## Deployment

We are deploying our FastAPI instance on AWS Lambda which is triggered via an API Gateway. In order to automate the process, we are using [AWS SAM](https://www.youtube.com/watch?v=tA9IIGR6XFo&ab_channel=JavaHomeCloud), which creates the stack required for the deployment and updates it as needed with just a couple of commands and without having to do anything manually on the AWS GUI. Refer to [this](https://www.eliasbrange.dev/posts/deploy-fastapi-on-aws-part-1-lambda-api-gateway/) blog post for more details.

The actual deployment happens through Github Actions. Look at [`.github/workflows/deploy_to_staging.yml`](.github/workflows/deploy_to_staging.yml) for understanding the deployment to `Staging` and [`.github/workflows/deploy_to_prod.yml`](.github/workflows/deploy_to_prod.yml) for `Production`. Make sure to set all the environment variables mentioned in [`docs/ENV.md`](docs/ENV.md) in the `Production` and `Staging` environments in your Github repository.

## Tests
- For testing, we use [`mongomock`](https://docs.mongoengine.org/guide/mongomock.html) package to mock our mongo database. To host this mock database, mongoDB process must run locally. Please install mongoDB following the instructions [here](https://www.mongodb.com/docs/manual/administration/install-community/). Ubuntu users may install using the command `pip install mongodb`.
- Create a folder `path/to/data/db` that mongoDB may use to store a local database. By default, `mongod` stores data in `/data/db`.
- Run the mongo daemon in a seperate terminal to start the host process in background.
```
mongod --dbpath path/to/data/db
```
- In case the above command does not work (lacks permissions, `data/db` not found), please check this [stackoverflow](https://stackoverflow.com/questions/22862808/mongod-command-not-found-os-x) thread.
- Finally, use the following command to run tests present in `app/tests`.
```
pytest
```

## Logs on Staging/Production

- The quizzing engine is setup for generating detailed application logs. You can see the logging config in `app/logger_config.py` and it logs to the stdout and stderr. As the quizzing engine is setup to run on AWS Lambda, a separate log shipper is configured which ships logs from this lambda function to the Loki instance (which is what we're using as our log aggregator).
- One can deploy the log shipper on AWS using the following steps:
  - Clone the official repo of loki onto your local. [Link Here](https://github.com/grafana/loki)
  - Navigate to `/tools/lambda-promtail`
  - Go through the `README.md` file in this folder. First step is to build the GO binary for the package and upload it to AWS ECR.
  - Running `docker build . -f tools/lambda-promtail/Dockerfile` from the root of the Loki repository will generate the image for you. Now upload it to ECR and note down the ECR URI of the image.
  - Now you can provision all the necessary resources by running a terraform script or a cloudformation script provided in the repo. We prefer cloudformation in this case.
  - Before running the cloudformation command, make sure to edit any required variables in your `template.yml` file. The only required thing in our case is updating the `MainLambdaPromtailSubscriptionFilter` resource. Update the `LogGroupName` for this resource. Point it to the log group name for your lambda function where your quiz engine backend is running.
  - Run this command on your local with the correct aws profile set:
    ```bash
    aws cloudformation create-stack \
    --stack-name NAME_OF_YOUR_STACK \
    --template-body file://template.yaml \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --region YOUR_REGION \
    --parameters \
        ParameterKey=WriteAddress,ParameterValue=YOUR_LOKI_HOST/loki/api/v1/push \
        ParameterKey=LambdaPromtailImage,ParameterValue=YOUR_ECR_REPO:TAG \
        ParameterKey=ExtraLabels,ParameterValue="env\,staging\,service\,quizBackend" \
        ParameterKey=SkipTlsVerify,ParameterValue="true"

    ```
  - This will deploy your lambda promtail and your quizzing engine backend will be shipping logs to this promtail which in turn will be shipping logs to your loki instance. Now have fun exploring the logs on your Grafana dashboard!
