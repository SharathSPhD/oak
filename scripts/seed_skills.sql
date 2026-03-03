-- Seed skills: insert probationary skills from filesystem into DB.
-- Run: psql $DATABASE_URL < scripts/seed_skills.sql
-- Safe to run multiple times (ON CONFLICT DO NOTHING).

INSERT INTO skills (name, category, description, trigger_keywords, status, filesystem_path)
VALUES
  (
    'event-bus-observer',
    'infra',
    'Implements the Observer pattern using an in-process async EventBus. '
    'Provides AgentEvent dataclass, EventSubscriber ABC, and a singleton EventBus '
    'that routes events to all registered subscribers. Used for agent lifecycle events, '
    'judge verdicts, and session state updates.',
    ARRAY['event', 'observer', 'pubsub', 'eventbus', 'subscriber', 'async'],
    'probationary',
    '/workspace/skills/probationary/SKILL-event-bus.md'
  ),
  (
    'task-state-machine',
    'infra',
    'Implements a StateMachine pattern for agent task lifecycle. '
    'Valid transitions: pending → in_progress → completed, pending → cancelled, '
    'in_progress → failed. Raises IllegalTransition on invalid moves. '
    'Used by the Orchestrator to track task progress.',
    ARRAY['task', 'state', 'statemachine', 'lifecycle', 'transition', 'orchestrator'],
    'probationary',
    '/workspace/skills/probationary/SKILL-task-state-machine.md'
  )
ON CONFLICT (name) DO NOTHING;
