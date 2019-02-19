# Python JSON Logging Library

Useful when creating Sanic applications that will run in a Kubernetes cloud environment, having centralised logging with Fluent-Bit. A bit specific, yes :)

## Installation

In your Pipenv app, command:

    pipenv install -e "git+ssh://git@github.com/speechgrinder/logger@master#egg=logger"

After that, you should have a VCS dependency in your Pipfile. Have fun!

## Configuration

Before starting the Sanic app, add:



If `KUBERNETES_PORT` environment variable is defined, all logs will be written
as JSON objects (one object per line), with all double quotes `"` removed.
Fluent Bit cannot digest those at the moment (1.0.4).

Otherwise, you should see human-readable log lines in the terminal.
