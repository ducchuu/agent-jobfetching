# Privacy and Data Lifecycle

[Back to README](../README.md)

## Local storage

Application code does not intentionally retain uploaded PDFs. It reads their bytes for extraction; the upload framework may temporarily spool data to disk. This is not a guarantee that an upload never touches disk.

The extracted profile is cached at `data/candidate_profile.json`. SQLite stores posting IDs/fingerprints, statuses, scores, and reasoning. Docker persists application data in its named volume.

The profile can contain a name, qualifications, languages, project descriptions, professional experience, and inferred target roles. Job-processing reasoning and logs may also contain sensitive free text.

## External flows

| Destination | Data and purpose |
|---|---|
| Anthropic | Extracted CV text during profile parsing; evaluation data when configured routes/fallbacks use Anthropic |
| OpenAI | Qualifications, languages, projects, experience summaries, target titles, and job text during configured evaluation calls |
| Discord | Job details and selected model-generated evaluation fields |
| Langfuse, when enabled | Execution traces that may include prompts and model completions |

The latest reported change removes the dedicated candidate-name field from the skills prompt. This is data minimization, not anonymization: project names, experience summaries, and generated text may still identify a person. Review the actual prompts and serialized payloads before using sensitive CVs.

Discord notifications do not deliberately attach the full CV or contact details, but model-generated fields may contain personal information. Review the notification format and generated content.

## Tracing

The intended configuration registers Langfuse callbacks only when both tracing credentials are supplied. Confirm that disabled tracing does not initialize external callbacks in the released configuration.

Do not enable tracing casually for real CVs. Review destination, access controls, retention, and deletion settings.

## Deletion and retention boundaries

See [deployment maintenance](deployment.md#maintenance) for deployment-specific local deletion commands.

Deleting local data does not delete:

- Discord messages;
- Langfuse traces;
- externally retained request logs or records;
- independent backups or exported logs.

Provider retention and data-use terms are external to this repository. Check current provider policies and account settings before processing personal data.

## Practical precautions

- Use a sanitized profile for demonstrations and screenshots.
- Exclude credentials, profiles, CVs, databases, and sensitive logs from Git and Docker builds.
- Protect remotely accessible profile/upload/trigger endpoints.
- Limit access to backups, logs, runner machines, and tracing projects.
- Do not describe self-hosting as fully local processing: provider APIs receive data.
