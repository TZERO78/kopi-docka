# /docs — Documentation Lookup for Kopi-Docka

Search the official documentation for Kopia, Docker, rclone, and storage backends.

## Usage

```
/docs <query>
/docs kopia retention policies
/docs docker inspect fields
/docs rclone s3 backend
/docs b2 credentials
```

## Instructions

You are helping a developer working on **kopi-docka**, a Python CLI wrapper around Kopia for Docker backup. Look up the query `$ARGUMENTS` in the relevant official documentation.

**Step 1 — Identify which source(s) to search:**

| Topic keywords | Primary source |
|---|---|
| kopia, snapshot, repository, policy, retention, maintenance, restore, connect, `kopia *` | https://kopia.io/docs/ |
| kopia CLI flags, subcommands | https://kopia.io/docs/reference/command-line/common/ |
| kopia policies / retention | https://kopia.io/docs/advanced/policies/ |
| docker run, inspect, container, volume, network, compose | https://docs.docker.com/reference/ |
| docker SDK, Engine API | https://docs.docker.com/engine/api/latest/ |
| rclone, rclone backend, rclone config | https://rclone.org/docs/ |
| s3, aws, minio | https://rclone.org/s3/ |
| gcs, google cloud storage | https://rclone.org/googlecloudstorage/ |
| azure blob | https://rclone.org/azureblob/ |
| b2, backblaze | https://rclone.org/b2/ |
| sftp, ssh | https://rclone.org/sftp/ |
| tailscale | https://tailscale.com/kb/ |

**Step 2 — Fetch and read the relevant page(s).** Use WebFetch to retrieve the documentation. If the first page doesn't fully answer the question, follow relevant links or try a WebSearch.

**Step 3 — Answer concisely** with:
- The exact CLI flags / API fields / config keys relevant to the query
- Any gotchas or non-obvious behavior
- A direct link to the source page
- If applicable: how this affects kopi-docka code (e.g. which file/method calls this)

Keep the answer focused. No need to summarize the entire page — only what's relevant to `$ARGUMENTS`.
