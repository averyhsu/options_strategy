import datetime as dt

from options_strategy.data.calendar import (
    ExpiryRules,
    build_expiry_table,
    load_sessions,
    session_dates,
    third_friday,
)

RULES = ExpiryRules()


def test_third_friday_examples() -> None:
    assert third_friday(2024, 3) == dt.date(2024, 3, 15)
    assert third_friday(2026, 6) == dt.date(2026, 6, 19)
    assert third_friday(2022, 4) == dt.date(2022, 4, 15)  # Good Friday itself


def test_sessions_skip_holidays_and_flag_early_closes() -> None:
    df = load_sessions(dt.date(2024, 7, 1), dt.date(2024, 7, 8))
    days = df["session"].to_list()
    assert dt.date(2024, 7, 4) not in days  # Independence Day
    row = df.filter(df["session"] == dt.date(2024, 7, 3)).row(0, named=True)
    assert row["early_close"] is True
    assert row["close_et"].hour == 13
    full = df.filter(df["session"] == dt.date(2024, 7, 5)).row(0, named=True)
    assert full["early_close"] is False
    assert (full["open_et"].hour, full["open_et"].minute) == (9, 30)


def test_good_friday_weekly_shifts_to_thursday() -> None:
    table = build_expiry_table(dt.date(2024, 3, 1), dt.date(2024, 3, 31), RULES)
    dates = set(table["expiry_date"].to_list())
    assert dt.date(2024, 3, 29) not in dates  # Good Friday 2024
    weekly = table.filter(
        (table["expiry_date"] == dt.date(2024, 3, 28)) & (table["root"] == "SPXW")
    )
    assert weekly.height == 1
    assert weekly["settlement"][0] == "PM"


def test_monthly_is_am_settled_spx_on_third_friday() -> None:
    table = build_expiry_table(dt.date(2024, 3, 1), dt.date(2024, 3, 31), RULES)
    monthly = table.filter(table["root"] == "SPX")
    assert dt.date(2024, 3, 15) in monthly["expiry_date"].to_list()
    assert set(monthly["settlement"].to_list()) == {"AM"}
    # PM weekly coexists on the monthly Friday in the modern era:
    both = table.filter(table["expiry_date"] == dt.date(2024, 3, 15))
    assert set(both["root"].to_list()) == {"SPX", "SPXW"}


def test_good_friday_2022_monthly_shifts_to_thursday() -> None:
    table = build_expiry_table(dt.date(2022, 4, 1), dt.date(2022, 4, 30), RULES)
    monthly = table.filter(table["root"] == "SPX")["expiry_date"].to_list()
    assert dt.date(2022, 4, 14) in monthly  # shifted off Good Friday 2022-04-15
    assert dt.date(2022, 4, 15) not in monthly


def test_era_correctness_no_tue_thu_before_2022() -> None:
    table = build_expiry_table(dt.date(2018, 6, 1), dt.date(2018, 6, 30), RULES)
    june_weeklies = table.filter(
        (table["root"] == "SPXW") & (table["expiry_date"] <= dt.date(2018, 6, 30))
    )["expiry_date"].to_list()
    assert june_weeklies, "expected some weeklies in June 2018"
    # June 2018 has no holidays, so no shift can create Tue/Thu dates:
    assert all(d.weekday() in (0, 2, 4) for d in june_weeklies)


def test_midweek_holiday_shifts_forward() -> None:
    # 2018-07-04 was a Wednesday holiday; CBOE convention moves the weekly to
    # the FOLLOWING business day, Thursday 07-05 (pre-Tue/Thu era, so this is
    # the only way a Thursday date appears in 2018).
    table = build_expiry_table(dt.date(2018, 6, 1), dt.date(2018, 7, 31), RULES)
    weeklies = set(table.filter(table["root"] == "SPXW")["expiry_date"].to_list())
    assert dt.date(2018, 7, 5) in weeklies
    assert dt.date(2018, 7, 4) not in weeklies
    assert dt.date(2018, 7, 3) not in weeklies


def test_monday_holiday_shifts_forward() -> None:
    # MLK Monday 2020-01-20 -> Tuesday 2020-01-21 (pre-Tue/Thu era).
    table = build_expiry_table(dt.date(2020, 1, 1), dt.date(2020, 1, 31), RULES)
    weeklies = set(table.filter(table["root"] == "SPXW")["expiry_date"].to_list())
    assert dt.date(2020, 1, 21) in weeklies
    assert dt.date(2020, 1, 20) not in weeklies


def test_thanksgiving_thursday_merges_into_friday() -> None:
    # Thanksgiving 2023-11-23: the Thursday weekly moves to Friday and dedupes,
    # so the week lists Mon/Tue/Wed/Fri only.
    table = build_expiry_table(dt.date(2023, 11, 1), dt.date(2023, 11, 30), RULES)
    wk = table.filter(
        (table["root"] == "SPXW")
        & (table["expiry_date"] >= dt.date(2023, 11, 20))
        & (table["expiry_date"] <= dt.date(2023, 11, 24))
    )["expiry_date"].to_list()
    assert dt.date(2023, 11, 23) not in wk
    assert wk.count(dt.date(2023, 11, 24)) == 1
    assert set(wk) == {
        dt.date(2023, 11, 20),
        dt.date(2023, 11, 21),
        dt.date(2023, 11, 22),
        dt.date(2023, 11, 24),
    }


def test_new_years_monday_does_not_leak_before_start() -> None:
    # 2024-01-01 (Monday holiday) must shift forward to 01-02, never backward
    # off the table's start boundary.
    table = build_expiry_table(dt.date(2024, 1, 1), dt.date(2024, 1, 31), RULES)
    dates = table["expiry_date"].to_list()
    assert min(dates) >= dt.date(2024, 1, 1)
    weeklies = set(table.filter(table["root"] == "SPXW")["expiry_date"].to_list())
    assert dt.date(2024, 1, 2) in weeklies


def test_tue_thu_present_in_modern_era() -> None:
    table = build_expiry_table(dt.date(2023, 6, 1), dt.date(2023, 6, 30), RULES)
    june_weeklies = [
        d
        for d in table.filter(table["root"] == "SPXW")["expiry_date"].to_list()
        if d <= dt.date(2023, 6, 30)
    ]
    weekdays = {d.weekday() for d in june_weeklies}
    assert {0, 1, 2, 3, 4} <= weekdays


def test_every_expiry_is_a_session() -> None:
    table = build_expiry_table(dt.date(2024, 1, 1), dt.date(2024, 12, 31), RULES)
    sess = session_dates(dt.date(2024, 1, 1), dt.date(2026, 3, 1))
    assert all(d in sess for d in table["expiry_date"].to_list())
