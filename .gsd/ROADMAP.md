# Interview-Portal Roadmap

## Status: ACTIVE

### Phase 1: Autonomous Jules Bug-Fixing Pipeline & Slack Dispatch (KAN-23)
- [x] Phase 1.1: Spec & Architecture definition (.gsd/SPEC.md)
- [x] Phase 1.2: Add session activities & event polling to `core/jules.py`
- [x] Phase 1.3: Create deduplication & dispatch service in `core/jules.py`
- [x] Phase 1.4: Wire 500 handler (`core/views.py`) and worker error handler (`run_worker.py`)
- [x] Phase 1.5: Unit tests for polling, dispatch, and deduplication (6/6 passed)
- [ ] Phase 1.6: Inbound Sentry Webhook endpoint (`/api/integrations/sentry/webhook/`) for event-driven triggering
- [ ] Phase 1.7: End-to-end verification and Slack notification testing
