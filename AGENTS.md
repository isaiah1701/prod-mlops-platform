# Repository development conventions

- Add complete parameter and return type hints to every new or modified Python
  function. Type fixture parameters and test functions as well as production
  code.
- Give every new or modified Python function a concise docstring.
- Create one module-level logger with `logging.getLogger(__name__)` in every
  Python module that defines functions.
- Log meaningful function lifecycle events and validation failures. Keep pure
  data transformations free of global logging configuration; configure handlers
  and levels only in application entry points.
- Never log secrets, credentials, or full sensitive datasets.
