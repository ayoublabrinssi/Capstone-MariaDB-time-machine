# AI log

I used Claude (Anthropic) as an assistant on this project. This file lists every use: what I asked, what the AI drafted, and what I decided, checked or changed myself. Prompts are copied with spelling and grammar fixed. The meaning is the same, and long ones are shortened with "...".

When the code changes, this log is updated so it still matches. New entries go at the bottom.

## My part

- I chose the area: system-versioned tables (area 3). I compared it with the optimizer (area 7) and picked area 3 because the result is visible, and because I can apply it to JPTrack, a vehicle tracking platform I worked on as a software engineer in Morocco.
- I decided to work alone after the rest of Team IV did not answer, and I told the supervisor.
- I chose the theme (Moroccan cities), the repository name and the finish date (27 November, before the final presentation on 3 December).
- I set the scope: the fleet example stays a small side example next to Wikipedia.
- I review every file before it is committed, and I merge every change myself.

## What the AI did

- Drafted the week plan and the first versions of the scripts, SQL and README text listed below.
- Ran the fetch script on my Mac, at my request, and reported the counts.

## Summary

| # | Date | Part | What the AI drafted | What I did |
|---|---|---|---|---|
| 1 | 2026-10-26 | data and repository files | `fetch/fetch.py`, `scripts/`, `compose.yaml`, `data/articles.txt`, `sql/01_schema.sql`, README draft | chose the theme (Moroccan cities) and the repository name; created the repository on GitHub; ran the fetch; reviewed the files before the commit |
| 2 | 2026-10-26 | plan | week-by-week plan to 3 December, each step mapped to the MariaDB evaluation criteria | chose area 3, the solo setup and the finish date; gave the AI the MariaDB evaluation prompt and the area instructions to plan against |
| 3 | 2026-10-26 | schema, loader, queries, tests | `fetch/prepare.py`, `sql/01_schema.sql`, `sql/02_load.sql`, `sql/queries.sql`, `sql/examples/`, `tests/tests.sql`, README update | asked for one bitemporal table next to the history table and for the JPTrack-style fleet example; reviewed the files and ran the tests on my Mac before the commit |
| 4 | 2026-10-27 | the page | `app/server.py`, `app/wikitext.py`, `app/style.css`, `scripts/run.sh`, `tests/test_app.py`, screenshots, README section | asked for the next step of the plan (the page), then asked for a side-by-side compare, a logo and a new design with a searchable city list and a calendar; chose the logo (a history clock on an article, option B of the ones I asked for); asked for separate month and year menus, a full-width layout and the technical panel; asked for a light/dark switch and for the tables and pictures that were missing from the articles; spotted the empty "(, also , ; ; )" where Arabic names were lost; asked to move the revision facts to a plain row above the article (no box, no edit summary); reported that the pictures did not wrap with the text like on Wikipedia; asked for a professional README that presents the project; use less padding, and explain more in the technical panel; reviewed the page and ran it on my Mac before the commit |

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
