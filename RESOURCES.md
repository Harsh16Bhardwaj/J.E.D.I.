# JEDI Model Deployment Resources

## Knowledge

- [Vercel Services](https://vercel.com/docs/services)
  Official description of independently built frontend and backend services, shared deployment URLs, routing, and service-level `includeFiles`. Use for JEDI monorepo deployment architecture.
- [Using the Python Runtime with Vercel Functions](https://vercel.com/docs/functions/runtimes/python)
  Official Python packaging and runtime guide. Use when diagnosing whether model files and Python dependencies are inside the deployed function.
- [Vercel Functions limits](https://vercel.com/docs/functions/limitations)
  Official bundle-size, memory, and duration limits. Use before changing the model bundle or dependency closure.
- [JEDI embedded model runbook](docs/MODEL_SERVING_RUNBOOK.md)
  Repository-specific release gates, health probes, registration sequence, ranking contract, and rollback procedure.

## Wisdom (Communities)

- [Vercel Community](https://community.vercel.com/)
  Practitioner support for deployment-specific behavior that is not fully covered by documentation. Use after collecting a minimal reproduction and deployment logs.
