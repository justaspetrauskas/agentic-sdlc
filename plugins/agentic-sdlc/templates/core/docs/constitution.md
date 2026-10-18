# Constitution: {{PROJECT_NAME}}

## Goal
(One or two sentences: what this project is for.)

## Principles
- (What matters most, in order.)

## Stack
- (Languages, frameworks, hosting.)

## Quality bar
- Typecheck, lint, unit tests for critical components, integration test per acceptance criterion.

## Protected paths
See `.sdlc/config.yml`. Changes there always need a human.

## Critical decisions
Agents decide everything else and record it in the spec. These always go to the owner:
- Anything this constitution does not cover yet, such as stack or hosting.
- A conflict with this constitution.
- A new external service, paid tool or dependency.
- Data model or API changes that are hard to undo or touch data users already stored.
- Security, privacy, money or legal implications.
- Product direction: scope that changes what the product is for, or a choice between two features.
