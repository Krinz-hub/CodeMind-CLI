# Order Processing Service

Multi-module application managing orders, inventory items, and persistent storage.

## Architecture
- `src/models.py`: Defines data entities (`Item`, `Order`).
- `src/storage.py`: Persistence repository for storing orders.
- `src/service.py`: Business logic for calculating tax, applying vouchers, and placing orders.
- `tests/test_service.py`: Test suite verifying order calculation and storage.
