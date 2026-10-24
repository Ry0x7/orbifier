# Project working instructions

- Every future commit in this project must have a new release tag. Use an annotated `vMAJOR.MINOR.PATCH` tag on the committed revision; never move or reuse an existing tag.
- Choose the next version from the existing tags (patch for fixes, minor for features, major for breaking changes). Keep `settings.py`, the fallback in `orbifier/config.py`, and the README version entry aligned before committing.
- When pushing a commit, push its release tag too so `.github/workflows/release.yml` builds and publishes the release. Verify the remote tag points to the intended commit.
