# Sample data

Three of the 45 articles, so the project can be tried without the 15-minute download:
Rabat (1,878 revisions), Ifrane (474) and Asilah (248), as they were on 26 October 2026.

Each file is the output of `fetch/fetch.py` for one article, gzipped: every revision with its
editor, time, size and comment, and the wikitext of the first revision of each quarter.

    scripts/start.sh --data sample      # or: scripts/install.sh --sample

The text and the edit histories come from the English Wikipedia and are licensed
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The authors are the editors
named in each revision. Source pages: [Rabat](https://en.wikipedia.org/wiki/Rabat),
[Ifrane](https://en.wikipedia.org/wiki/Ifrane), [Asilah](https://en.wikipedia.org/wiki/Asilah).
