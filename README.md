# Python JSON Logging Library

Useful when creating Sanic applications that will run in a Kubernetes cloud environment, having centralised logging with Fluent-Bit. A bit specific, yes :)


## Installation

First, create a `$HOME/.netrc` file, containing your personal github access token (create one if not available):

    machine github.com login <github_id> password <personal_access_token>

After netrc is set up, in your application execute the command:

    pipenv install -e "git+https://github.com/speechgrinder/logger@master#egg=logger"

After that, you should have a VCS dependency in your Pipfile. Have fun!


## Usage

Before starting the Sanic app, setup logging with it:

    import logger

    app = create_app()
    logger.setup_logging(app)
    app.run(host="0.0.0.0", port=8000)

to get a named logger object:

    import logger

    log = logger.get_log('recorder')


## Configuration

If `KUBERNETES_PORT` environment variable is defined, all logs will be written
as JSON objects (one object per line), with all double quotes `"` removed.
Fluent Bit cannot digest those at the moment (1.0.4).

Otherwise, you should see human-readable log lines in the terminal.

In unit tests, no logging should be set up, as the test framework
takes care of setting up the logs properly.
