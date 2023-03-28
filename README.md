# Quiz Backend

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![codecov](https://codecov.io/gh/avantifellows/quiz-backend/branch/main/graph/badge.svg)](https://codecov.io/gh/avantifellows/quiz-backend)
[![Discord](https://img.shields.io/discord/717975833226248303.svg?label=&logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2&style=flat-square)](https://discord.gg/29qYD7fZtZ)

The backend for a generic mobile-friendly quiz engine created using FastAPI and MongoDB! The frontend can be found [here](https://github.com/avantifellows/quiz-frontend).

## Installation

### Local DB Setup

- The following steps are for a Mac.
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

Simply run:

```bash
chmod +x startServer.sh
./startServer.sh
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


You can pass arguments to the `startServer` script.
- `--freshSync` : Passing this argument means you're telling the script to take a fresh sync from the cloud DB to your local DB. By default, this is false.
- `--source staging` or `--source prod` : When `--freshSync` is specified, a source is also needed. Whether you need to sync from prod db or staging db. Note: Currently it might take 10-15 minutes for the sync process to be done. We're working on improving this.

Example:
```bash
./startServer.sh --freshSync --source prod
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
