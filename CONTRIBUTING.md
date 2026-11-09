# Contributing

Short rules that keep the project easy to work on.

## Workflow (GitHub Flow)

1. Branch from `main`: `feature/short-description`, `fix/short-description` or `docs/short-description`.
2. Make small commits. Run `make check` before you push.
3. Open a pull request using the template. CI (lint and tests) must be green.
4. One review, then squash or merge. Delete the branch.

`main` is always deployable. Do not push to it directly.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): subject`.

| Type | Use for | Version effect |
|------|---------|----------------|
| `feat` | new behaviour | minor |
| `fix` | bug fix | patch |
| `docs`, `test`, `chore`, `ci`, `refactor` | everything else | none |
| `feat!` or a `BREAKING CHANGE:` footer | incompatible change | major |

Examples: `feat(api): add custom aliases`, `fix: reject urls with spaces`.

## Before you open a pull request

- [ ] `make check` passes (lint and unit tests)
- [ ] New behaviour has a test
- [ ] New settings are in `.env.example` and in the README table
- [ ] Operational changes are in `docs/operations.md`
- [ ] User-visible changes are in `CHANGELOG.md`

## Local setup

```bash
python3 -m venv venv && source venv/bin/activate
make install-dev
make check
```

Optional: `pip install pre-commit && pre-commit install` runs the formatters on every commit.

## Releases

Versions follow [Semantic Versioning](https://semver.org/). Update `CHANGELOG.md` and `api/__init__.py`, then tag: `git tag -a v0.3.0 -m "Release 0.3.0" && git push --tags`.
