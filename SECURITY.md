# Security policy

Pollie is a teaching project, but it is built to be reviewed like a real one.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Email the maintainers (see the repository owner's profile) with what you found and how to reproduce it. You will get an answer within a few working days.

## What the project already does

- Validates all input: poll text and option lengths, option ownership, voter id length.
- Escapes nothing in the API (it returns JSON) and the frontend writes user-supplied text with `textContent`, never as HTML.
- Keeps secrets out of the repository: `.env` files are ignored and `.env.example` contains no real values.
- Parameterised SQL only, never string concatenation.

## Known limits (by design, for teaching)

- No authentication or rate limiting. Put it behind Nginx or an API gateway and add them there.
- No TLS in the app. Terminate TLS in front of it.
- Anyone who can reach the API can create polls and vote. `voter_id` is chosen by the client, so one person can vote more than once by changing it.
