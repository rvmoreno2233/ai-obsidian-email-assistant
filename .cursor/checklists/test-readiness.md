# Test Readiness Checklist

- [ ] New behavior has unit tests
- [ ] Failure paths tested where relevant
- [ ] Graph tests use `MockGraphBackend`
- [ ] Vault tests use `tmp_vault` fixture
- [ ] No network calls in tests
- [ ] `pytest` run locally and passing

Commands:

```bash
pytest
pytest -v tests/test_<module>.py
```
