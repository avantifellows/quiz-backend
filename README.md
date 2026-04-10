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

- **Python 3.12** is required. Create a virtual environment:
  ```bash
  python3.12 -m venv venv
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

- Copy `.env.example` to `.env` and set all the environment variables as mentioned in [`docs/ENV.md`](docs/ENV.md). The default value points to a local MongoDB instance — no changes needed for local development.

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

## Deployment

The backend is deployed on **ECS Fargate** (ARM64/Graviton) for both testing and production environments. Deployment is automated via GitHub Actions:

- **Testing** (`quiz-backend-testing.avantifellows.org`): deploys on CI success on `main` via `.github/workflows/deploy_ecs_testing.yml`
- **Production** (`quiz-backend.avantifellows.org`): deploys on CI success on `release` via `.github/workflows/deploy_ecs_prod.yml`

Infrastructure is managed by Terraform in `terraform/testing/` and `terraform/prod/`. Environment variables (`MONGO_AUTH_CREDENTIALS`, `MONGO_DB_NAME`) are configured in the ECS task definitions via Terraform — see `terraform/*/ecs.tf` and [`docs/ENV.md`](docs/ENV.md) for details.

## Tests
Tests run against a real MongoDB instance (local or CI service). The test harness forces `MONGO_DB_NAME=quiz_test` automatically, so tests never touch a production database.

Make sure MongoDB is running locally and set the required environment variables before running tests:

```bash
# Option 1: source .env (use set -a to export all variables)
set -a; source .env; set +a; pytest

# Option 2: export manually
export MONGO_AUTH_CREDENTIALS='mongodb://127.0.0.1:27017'
export MONGO_DB_NAME='quiz_test'
pytest
```

## Logs

Application logs are configured in `app/logger_config.py` and output to stdout/stderr. On ECS Fargate, logs are sent to CloudWatch Logs automatically.
