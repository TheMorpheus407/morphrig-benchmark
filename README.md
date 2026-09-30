# MorphRig benchmark

Raw runs of the MorphRig benchmark: an original cyberpunk character with a
modeled body, rig and skinning, 96 named motion and pose entries, a facial rig
with a spoken line, and a Blender to Unreal Engine to Linux delivery, built by
an AI model in a single run.

## Task

Every model received the same inputs:

- [`SPEC.md`](SPEC.md): the assignment
- [`required_animations.csv`](required_animations.csv): the motion inventory
- [`environment.json`](environment.json): the measured reference host
- [`prompt.txt`](prompt.txt): the prompt that started the run

## Runs

One folder per model. Each folder contains the files of the model's workspace
at the end of its run, including its own copy of the inputs above.

| Folder | Model | Run |
|---|---|---|
| [`Claude-Opus-5.5/`](Claude-Opus-5.5/) | Claude Opus 5.5 | 2026-09-23 |
| [`GPT-6-Astra/`](GPT-6-Astra/) | GPT-6 Astra | 2026-09-26 |
| [`Claude-Sonnet-5.5/`](Claude-Sonnet-5.5/) | Claude Sonnet 5.5 | 2026-09-29 |
| [`GPT-6.1-Sol/`](GPT-6.1-Sol/) | GPT-6.1 Sol | 2026-09-29 |

Packaged Linux builds and other large parts are attached to the GitHub
release of each run; `RELEASE_ASSETS.txt` in the run folder lists them with
sizes and SHA-256 checksums. Unreal and Blender generated folders, caches and
harness configuration are left out (see [`.gitignore`](.gitignore)).

## License

MIT, see [LICENSE](LICENSE). Third-party components keep their own licenses;
each run lists them in its `THIRD_PARTY_ASSETS.csv`.
