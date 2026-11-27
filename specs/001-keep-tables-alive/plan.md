# Plan 001
- `refresh_expiration(client, dataset, now)`: skip views and far expirations; update; on
  `Forbidden`, `renew_by_copy` (copy to `<table>__renew`, delete, copy back, delete the copy,
  restore description, labels and expiration).
- `main`: run it over `client.list_datasets()`.
- Tests with a fake client: skip, extend, renew by copy in the safe order.
