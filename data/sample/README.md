# Sample data

Three of the 45 articles, so the project can be tried without the 15-minute download. They are as they were on 26 October 2026.

[← Back to the README](../../README.md)

| Article | Revisions | File |
|---|---|---|
| [Rabat](https://en.wikipedia.org/wiki/Rabat) | 1,878 | `Rabat.json.gz` |
| [Ifrane](https://en.wikipedia.org/wiki/Ifrane) | 474 | `Ifrane.json.gz` |
| [Asilah](https://en.wikipedia.org/wiki/Asilah) | 248 | `Asilah.json.gz` |

Each file is the output of `fetch/fetch.py` for one article, gzipped: every revision with its editor, time, size and comment, and the wikitext of the first revision of each quarter.

```sh
scripts/start.sh --data sample      # or: scripts/install.sh --sample
```

## License

The text and the edit histories come from the English Wikipedia and are licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The authors are the editors named in each revision.
