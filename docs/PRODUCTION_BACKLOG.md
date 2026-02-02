# Production Backlog

Items deferred from initial implementation for production readiness. Track these for future phases.

## Async Task Processing
- [ ] **Celery + Redis** - Replace synchronous action execution with async tasks
  - Action nodes (send_email, send_alert, webhook) should run in background
  - Large file hash calculation should be async
  - Report generation should be async
  - Notification delivery should be async

## Infrastructure
- [ ] **Docker containerization** - Dockerfile and docker-compose.yml
- [ ] **Nginx configuration** - Reverse proxy, static file serving
- [ ] **Redis caching layer** - Session storage, query caching
- [ ] **S3 storage** - django-storages configuration for production file storage
- [ ] **PostgreSQL** - Currently using SQLite for development

## Real-time Features
- [ ] **Django Channels / WebSockets** - Real-time notifications instead of polling
- [ ] **Server-Sent Events** - Alternative to WebSockets for simpler real-time

## Security Hardening
- [ ] **Rate limiting** - Login attempts, API endpoints
- [ ] **OCSP/CRL checking** - X.509 certificate revocation verification
- [ ] **PGP keyserver integration** - Key lookup and verification
- [ ] **Content Security Policy headers**
- [ ] **Security audit**

## Performance
- [ ] **Database connection pooling** - PgBouncer or similar
- [ ] **Query optimization audit** - N+1 queries, slow query logging
- [ ] **CDN for static assets**
- [ ] **Full-text search** - PostgreSQL SearchVectorField for package/document search

## Monitoring
- [ ] **Application monitoring** - Sentry or similar
- [ ] **Health check endpoints** - /health, /ready
- [ ] **Metrics collection** - Prometheus/Grafana
- [ ] **Log aggregation** - Structured logging, ELK stack

## Future Features (Out of Scope)
- [ ] **Webhook action nodes** - External system integration
- [ ] **Mobile app / PWA**
- [ ] **SSO integration** - SAML/OIDC beyond PKI
- [ ] **Multi-language (i18n)**
- [ ] **Advanced reporting** - Custom report builder, scheduled reports

---

*Reference this file in CLAUDE.md for context on deferred items.*
