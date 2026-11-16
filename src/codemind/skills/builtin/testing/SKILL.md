---
name: testing
version: 1.0.0
description: Hermetic automated testing strategy, unit test design, mock isolation, edge case coverage, and assertion discipline.
category: testing
triggers:
  manifests:
    - "pytest.ini"
    - "jest.config.js"
    - "vitest.config.ts"
  globs:
    - "*test*.py"
    - "*spec*.ts"
    - "*test*.ts"
    - "*test*.js"
  keywords:
    - "test"
    - "tests"
    - "testing"
    - "unit test"
    - "unit tests"
    - "integration test"
    - "integration tests"
    - "mock"
    - "mocks"
    - "coverage"
    - "assert"
    - "assertion"
    - "assertions"
    - "pytest"
    - "unittest"
    - "jest"
    - "vitest"
required_tools:
  - read_file
  - create_file
  - apply_patch
  - run_command
dependencies: []
conflicts: []
workflow_steps:
  - "1. Inspect existing test suites to identify test frameworks (pytest, unittest, jest, vitest), directory patterns, and mocking utilities."
  - "2. Identify target units under test and establish test boundaries (unit vs integration)."
  - "3. Follow the Arrange-Act-Assert (AAA) pattern with descriptive test function naming."
  - "4. Mock external side effects (network requests, disk writes, time dependencies) using standard mock adapters."
  - "5. Cover edge cases: boundary numbers (0, -1, max), empty collections, null inputs, and unexpected exceptions."
  - "6. Run the test command and verify that tests execute deterministically and pass without flakiness."
constraints:
  - "Never write tests that perform real external network calls or require live internet access."
  - "Avoid multiple unrelated assertions in a single unit test; keep test focus sharp."
  - "Do not mock the system under test; mock only its external dependencies."
verification:
  - "Execute test runner and confirm all tests pass cleanly with zero failures or skipped errors."
enabled: true
---

# Automated Testing & Verification Workflow

## 1. Test Pyramid & Isolation
- **Unit Tests:** Hermetic, sub-millisecond execution. Tests business logic in memory with mocked IO.
- **Integration Tests:** Verify communication between two or more modules (e.g. SQLite database and repository class).
- **Hermetic Guarantee:** Tests must pass in an offline, disconnected sandbox.

## 2. Arrange-Act-Assert (AAA) Standard
```python
def test_calculate_total_with_discount() -> None:
    # Arrange
    cart = ShoppingCart()
    cart.add_item("item_1", price=100.0)

    # Act
    total = cart.calculate_total(discount_percent=10)

    # Assert
    assert total == 90.0
```
