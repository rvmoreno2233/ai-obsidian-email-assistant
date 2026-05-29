# Security Review Checklist

- [ ] No hardcoded secrets or client IDs in code
- [ ] `.env` not committed
- [ ] MSAL cache stays outside repo
- [ ] No full email bodies in logs
- [ ] Studio not bound to `0.0.0.0` without auth
- [ ] `AUTO_SEND_MODE` unchanged or explicitly approved
- [ ] Tests use synthetic fixtures only
- [ ] LLM mode documented if email text sent to Ollama
