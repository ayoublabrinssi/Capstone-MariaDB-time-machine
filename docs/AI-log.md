# AI log

This project is my work, done with the help of AI. I used Claude (Anthropic) as an assistant. I chose what to build and how, gave the instructions for each step, checked the results, and decided what stays. The AI drafted code and text from those instructions and ran commands on my Mac when I asked.

This file lists every use of AI that put something into this repository: what I did, where the AI helped, and my prompts. Planning talk, meeting preparation and study notes are left out. Prompts are copied with spelling and grammar fixed. The meaning is the same, and long ones are shortened with "...".

When the code changes, this log is updated so it still matches. New entries go at the bottom.

## My work

- **The area and the idea.** I chose system-versioned tables (area 3) over the optimizer (area 7), because the result is visible and because I can apply it to JPTrack, the vehicle tracking platform I worked on as a software engineer in Morocco.
- **The project setup.** I decided to work alone after the rest of Team IV did not answer, and I told the supervisor. I chose the theme (Moroccan cities), the repository name and the finish date (27 November, before the final presentation on 3 December).
- **The design.** I asked for a bitemporal table next to the history table, so a wrong date can be corrected, and for the fleet example from JPTrack. I kept the fleet example small, next to Wikipedia.
- **The page.** I directed it round by round: the compare view, the logo (I chose option B), the city list and calendar, the light and dark modes, the layout, the technical panel. I found the bugs while testing it, like the Arabic names that were lost and the pictures that did not wrap with the text.
- **The measurements.** I picked the four features of week 6 and their order, and decided to keep the partitions even though they slow the single-article query.
- **MariaDB.** I presented the project to MariaDB in November and asked two questions: why the table is sorted by the end date, which makes an old date slow, and why I needed my own columns to keep the real dates. I brought back their answer: system versioning is designed to record from the day it is switched on, not to import past history. The last part of the project is built on that answer.
- **The final round.** I asked to take the project further from MariaDB's answer: find the problems, fix each one and test it. I asked to check the project with MariaDB's evaluation prompt and to fix what it found.
- **The findings.** I asked for the findings to be written so that someone who is not technical can follow them, and sent back the explanations that were not clear until they were.
- **Checking.** I check the files and the results before each commit, and I commit and push every change myself.

## Where the AI helped

- **Drafting.** The first version of the scripts, SQL, page code, tests and README text, from my instructions. I then asked for changes until it was what I wanted. The prompts below show those rounds.
- **Running.** The fetch, the tests and the measurements on my Mac, when I asked, with the results reported back to me.
- **Reviewing.** Running MariaDB's evaluation prompt on the project to find what was still weak.

## Summary

| # | Date | Part | What I did | Where the AI helped |
|---|---|---|---|---|
| 1 | 2026-10-26 | data and repository files | chose the theme (Moroccan cities) and the repository name; created the repository on GitHub; ran the fetch; checked the files before the commit | drafted `fetch/fetch.py`, `scripts/`, `compose.yaml`, `data/articles.txt`, `sql/01_schema.sql` and the first README |
| 2 | 2026-10-26 | plan | chose area 3, working solo and the finish date; gave the AI the MariaDB evaluation prompt and the area instructions to plan against | drafted a week-by-week plan to 3 December, each step mapped to the evaluation criteria |
| 3 | 2026-10-26 | schema, loader, queries, tests | asked for one bitemporal table next to the history table and for the JPTrack-style fleet example; checked the files and ran the tests on my Mac before the commit | drafted `fetch/prepare.py`, `sql/01_schema.sql`, `sql/02_load.sql`, `sql/queries.sql`, `sql/examples/`, `tests/tests.sql` and the README update |
| 4 | 2026-10-27 | the page | asked for the page, then for a side-by-side compare, a logo and a new design with a searchable city list and a calendar; chose the logo (option B of the ones I asked for); asked for separate month and year menus, a full-width layout and the technical panel; asked for a light/dark switch and for the tables and pictures that were missing; found the empty "(, also , ; ; )" where Arabic names were lost; asked to move the revision facts to a plain row above the article; found that the pictures did not wrap with the text like on Wikipedia; asked for less padding, more explanation in the technical panel, and a professional README; tested the page on my Mac before the commit | drafted `app/server.py`, `app/wikitext.py`, `app/style.css`, `scripts/run.sh`, `tests/test_app.py`, the screenshots and the README section, and changed them after each round |
| 5 | 2026-10-28 | one-command setup | asked for one command that sets up and runs the project for someone trying it locally; decided that the user chooses at the start between the fixed date data (to compare with the test results) and the newest data, and that the README says what changes; ran it on my Mac before the commit | drafted `scripts/start.sh`, `data/snapshot.tsv`, `--snapshot` in `fetch/fetch.py`, one page test and the README quick start |
| 6 | 2026-11-03 | measurements, session time travel, retention, edit wars | picked the four features (measurements, time travel for a whole session, retention, an edit-war detector) and their order; ran the measurements on my Mac and chose to keep the partitions although they slow the single-article query; checked the result before the commit | drafted `scripts/measure.py`, `scripts/measure.sh`, `docs/measurements.md`, `sql/examples/retention.sql`, the session cross-check and the "Edit wars" list in the page, queries 11 and 12, five database checks and two page tests, and the README update |
| 7 | 2026-11-13 | the old-date fix, limits, import tutorial, notes for MariaDB, CI | brought the question and MariaDB's answer from the meeting; asked to take the project further from it: the problems found, the fix for each, and what we do about them, all tested; asked to check the result with MariaDB's evaluation prompt, twice, and to fix what it found each time; checked the changes and the results before the commit | drafted section 4 of `scripts/measure.py` and `docs/measurements.md`, the "A shorter way" part of the page, query 13, `sql/examples/limits.sql`, `sql/examples/import_history.sql`, `sql/examples/live_edit.sql`, `scripts/backup_check.sh`, `scripts/trust_check.sh`, `scripts/text_cost.py`, `scripts/growth.py`, `docs/import-tutorial.md`, `docs/contributions.md` and `.github/workflows/ci.yml`; the exact text of a revision (`app/exact.py`), the page code split into `app/db.py`, `app/views.py` and `app/server.py`, a read-only database user for the page (`scripts/page_user.sh`), the sample in `data/sample/`; corrections to wrong numbers in the README and `docs/measurements.md`; twenty database checks, sixteen page tests and the sixteen tests of `tests/test_fetch.py`; ran the evaluation prompt and the tests |
| 8 | 2026-11-14 | the findings, written for everyone | asked for the findings and what MariaDB can use from them to be explained in the README and in a folder of their own, easy to follow for someone who is not technical, with interactive figures; sent back the first explanations of the clock and old-date findings because they were not clear, and asked for a step-by-step story with a concrete example instead; checked the pages before the commit | drafted `docs/findings/` (an index, seven pages and `explorer.html`), the "What we found" section of the README and the shorter `docs/contributions.md` |

## Prompts

### 1. Data and files (26 Oct 2026)

> Prepare the data and the files for the project.

### 2. Plan (26 Oct 2026)

> Make the plan to follow so I stay on track. Follow the evaluation prompt and the instructions MariaDB asks for.

### 3. Schema, loader, queries and tests (26 Oct 2026)

> Let's complete the work: the schema, loading the real edit dates, the queries and the tests for week 2.

### 4. The page (27 Oct 2026)

> Go for the next part: the page where you pick a city and a date and see the article.

> Add a side-by-side compare.

> The page looks too plain. Make a logo with the logo skill, improve the design, and use proper components: a calendar for the dates and a city list I can search, not a plain native select.

> Fix the calendar: I can't change the month or the year, make them separate. Use the full width of the screen, and add the technical side: show how MariaDB answers.

> Add a switch in the top corner to change between dark and light mode. The articles don't show tables or images, add them.

> Reduce the padding and margins on the sides of the article. The technical part could use more info.
>
> The revision data: put it as a card on top of the article so the article uses that space and is not so long.

> Why does it show "(, also , ; ; )"? Arabic is not supported, fix it.

> Put the facts before the article, on top, and the article below. Drop the edit summary, we don't care about it. And lose the box around them.

> The images don't look good: they have a dedicated space on the side. Make the text wrap around them like on Wikipedia.

> Work on the README: it should be professional and present the project.

### 5. One-command setup (28 Oct 2026)

> If someone wants to run the project locally, make a setup with one command that sets it up and runs it.

> In the setup, let them choose the fixed date or the newest data. Say in the README what will be different, and that the tests were done on the fixed date data.

> Ask it at the start. Next to the fixed date, say to choose it to compare with the test results. For the newest, say the results may differ from the test results.

### 6. Measurements, session time travel, retention, edit wars (3 Nov 2026)

> ... Now we need to add more features ...

> A, B, C, then D.

A to D were the four features in the title, in that order.

### 7. The old-date fix, limits, import tutorial, notes for MariaDB, CI (13 Nov 2026)

> Now we are going to work on finalizing the project and making it ready for the final submission. Set up all the tests, organize them, and let me see if you found any bug. Also work on the next steps we set and any way we can take the project further. And mention everything we found: all the problems, the fixes we made for them, and what still needs work.

### 8. The findings, written for everyone (14 Nov 2026)

> Make sure the README is good and looks good. I want it to include the findings: what we found, and what we think is useful for MariaDB. Add a folder with the details of each finding: the idea behind it, how we found it, and the solutions we found that work to get around it. I would like those files to be interactive and easy to understand, so people can follow them without being too technical ...

Before this, on the findings explained one by one:

> Explain this more. That graph is not showing anything. Explain how the versions overlap, why this is a problem, what it means, and whether there is a way to fix it.
