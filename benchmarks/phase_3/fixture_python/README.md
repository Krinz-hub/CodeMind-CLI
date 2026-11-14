# Task Manager Service

In-memory task tracking library designed for developer task queues.

## Architecture
- `src/task_manager.py`: Core `TaskManager` class providing `create_task`, `complete_task`, `list_tasks`, and `filter_by_tag`.
- `tests/test_task_manager.py`: Unit test suite testing task state transitions and filtering.

## Running Tests
```bash
python3 -m unittest discover -s tests
```
