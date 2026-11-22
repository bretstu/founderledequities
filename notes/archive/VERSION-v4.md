# v4 -- the panel, plus a per-filing history

Everything in v3, and a second output: the chief executive's stake after
every filing they made.

    python -m fle.cli history --universe universe/sp500-2026-08-25.csv \
        --since 2016-01-01 --out history.csv

THE WALK IS THE PANEL'S WALK, RUN FORWARDS. Newest-first, the first filing to
report a group settles it; oldest-first, each filing overwrites the group it
reports. Both end at the newest filing per group, so the last snapshot must
equal the panel's figure -- reported per company as `matches_panel`, and true
on all five verified companies.

Three things become time-varying:

    the class list      today's cover page names today's classes, and Block's
                        "Common Stock" WAS the class in 2019
    the denominator     Tesla went from 3.33bn shares to 3.95bn in ten years
    splits              the percentage is immune; the share count is not

ONE SNAPSHOT PER DAY, NOT PER FILING. Zuckerberg files two Forms 4 for the
same day and splits the vehicles between them -- his own remarks say which
goes where. Both settle exactly right, but a snapshot after the first is true
of that document and false of the position. The day's last filing settles the
day, which is the rule the panel already uses for the newest filing overall.
